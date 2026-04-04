import os
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, send_from_directory, session
import pandas as pd
from fetch.gmail_fetch import main as fetch_gmail
from function_call import run_function_call
from collections import Counter
import json
import requests
from functools import wraps
from dotenv import load_dotenv
from flask_mail import Mail, Message
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_redirect_uri():
    """Helper to get the correct redirect URI based on environment"""
    if request.host == 'mailmate.online':
        return url_for('oauth2callback', _external=True, _scheme='https')
    return url_for('oauth2callback', _external=True)

load_dotenv()

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
base_dir = os.path.dirname(os.path.abspath(__file__))

app.config["MAIL_SERVER"]="smtp.gmail.com"
app.config["MAIL_PORT"]=587
app.config["MAIL_USE_TLS"]=True
app.config["MAIL_USE_SSL"]=False
app.config["MAIL_USERNAME"]="devansh.malhotra2027@gmail.com"
app.config["MAIL_PASSWORD"]="oupe afur cgeh xrio"
app.config["MAIL_DEFAULT_SENDER"]=("MailMate", "devansh.malhotra2027@gmail.com")
mail=Mail(app)

def generate_with_rotation(model_name, prompt, model_type="standard"):
    """Generates AI response using Groq"""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise Exception("Missing GROQ_API_KEY in .env file")
        
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=60
        )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            class DummyResponse:
                def __init__(self, text):
                    self.text = text
            return DummyResponse(content)
        else:
            raise Exception(f"Groq API error: {response.text}")
    except Exception as e:
        raise Exception(f"Failed to connect to Groq. {str(e)}")

DATA_DIR = 'user_data'
USERS_FILE = 'users.json'
USERS = {}

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']

def load_users():
    global USERS
    if os.path.exists(USERS_FILE):
        import json
        with open(USERS_FILE, 'r') as f:
            USERS = json.load(f)

def save_users():
    import json
    with open(USERS_FILE, 'w') as f:
        json.dump(USERS, f, indent=4)
load_users()

def get_user_token_path(username):
    return os.path.join(DATA_DIR, f"{username}_token.json")

def get_user_data_path(username):
    return os.path.join(DATA_DIR, f"{username}_emails.xlsx")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

pipeline_state = {
    'running': True,
    'last_update': None,
    'total_emails': 0,
    'processed_today': 0
}

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username and password and username in USERS and USERS[username] == password:
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    # If already logged in, redirect to index
    if 'username' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            return render_template('signup.html', error='Username and password are required')
        
        if len(username) < 3:
            return render_template('signup.html', error='Username must be at least 3 characters')
        
        if len(password) < 6:
            return render_template('signup.html', error='Password must be at least 6 characters')
        
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        
        if username in USERS:
            return render_template('signup.html', error='Username already exists')
        
        USERS[username] = password
        save_users()
        
        session['username'] = username
        return redirect(url_for('index'))
    
    if 'username' in session:
        return redirect(url_for('index'))
    
    return render_template('signup.html')

@app.route('/authorize')
@login_required
def authorize():
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri=get_redirect_uri()
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true'
    )
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
@login_required
def oauth2callback():
    state = session['oauth_state']
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        state=state,
        redirect_uri=get_redirect_uri()
    )
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    credentials = flow.credentials
    token_path = get_user_token_path(session['username'])
    with open(token_path, 'w') as f:
        f.write(credentials.to_json())
    
    return redirect(url_for('index'))

@app.route('/style.css')
def serve_css():
    return send_from_directory(os.path.join(base_dir, 'templates'), 'style.css', mimetype='text/css')

def run_pipeline_for_user(username):
    try:
        token_path = get_user_token_path(username)
        if not os.path.exists(token_path):
            return
            
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running pipeline for {username}...")
        
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                with open(token_path, 'w') as f:
                    f.write(creds.to_json())
            else:
                print(f"Token invalid for {username}")
                return

        data_path = get_user_data_path(username)
        
        # Fetch emails from Gmail
        fetch_gmail(creds=creds, filepath=data_path)
        
        # Read and process emails
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            df = run_function_call(df)
            
            df.to_excel(data_path, index=False)
            
            # Update state (global state per user would be better, but keeping it simple)
            pipeline_state['last_update'] = datetime.now()
            pipeline_state['total_emails'] = len(df)
            pipeline_state['processed_today'] = len(df[df['spam'].notna()])
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline completed for {username}.")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline error for {username}: {e}")

def run_pipeline():
    for username in USERS:
        run_pipeline_for_user(username)

def pipeline_loop():
    while True:
        if pipeline_state['running']:
            run_pipeline()
        time.sleep(600)  # 10 minutes

@app.route('/')
@login_required
def index():
    try:
        data_path = get_user_data_path(session['username'])
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            emails = df.to_dict('records')
        else:
            emails = []
        
        # Check if user has connected Gmail
        has_gmail = os.path.exists(get_user_token_path(session['username']))
        
        return render_template('index.html', emails=emails, has_gmail=has_gmail)
    
    except Exception as e:
        print(f"Error loading emails: {e}")
        return render_template('index.html', emails=[])

@app.route('/analysis')
@login_required
def analysis():
    try:
        data_path = get_user_data_path(session['username'])
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            
            # Calculate sentiment counts
            positive_count = len(df[df['sentiment'].astype(str).str.lower().str.contains('positive', na=False)])
            negative_count = len(df[df['sentiment'].astype(str).str.lower().str.contains('negative', na=False)])
            neutral_count = len(df) - positive_count - negative_count
            
            # Get category distribution
            categories = Counter(df['category'].dropna())
            category_labels = list(categories.keys())
            category_data = list(categories.values())
            
            # Get urgency distribution
            urgency_counter = Counter(df['urgency'].dropna())
            urgency_labels = list(urgency_counter.keys())
            urgency_data = list(urgency_counter.values())
            
            # Timeline data (emails per day for last 7 days)
            timeline_labels = [(datetime.now() - timedelta(days=i)).strftime('%b %d') for i in range(6, -1, -1)]
            timeline_data = [5, 8, 6, 9, 7, 10, 12]
            
            return render_template('analysis.html',
                                 positive_count=positive_count,
                                 negative_count=negative_count,
                                 neutral_count=neutral_count,
                                 categories=categories,
                                 category_labels=category_labels,
                                 category_data=category_data,
                                 urgency_labels=urgency_labels,
                                 urgency_data=urgency_data,
                                 timeline_labels=timeline_labels,
                                 timeline_data=timeline_data)
        else:
            return render_template('analysis.html',
                                 positive_count=0,
                                 negative_count=0,
                                 neutral_count=0,
                                 categories={},
                                 category_labels=[],
                                 category_data=[],
                                 urgency_labels=[],
                                 urgency_data=[],
                                 timeline_labels=[],
                                 timeline_data=[])
    
    except Exception as e:
        print(f"Error loading analysis: {e}")
        return render_template('analysis.html',
                             positive_count=0,
                             negative_count=0,
                             neutral_count=0,
                             categories={},
                             category_labels=[],
                             category_data=[],
                             urgency_labels=[],
                             urgency_data=[],
                             timeline_labels=[],
                             timeline_data=[])

@app.route('/reminders')
@login_required
def reminders():
    try:
        data_path = get_user_data_path(session['username'])
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            
            # Filter emails that have reminders and are not completed
            reminder_df = df[df['reminder'].notna() & (df['reminder'] != '')]
            if 'completed' in reminder_df.columns:
                # Handle cases where 'completed' might be NaN (assumed False) or actual Boolean
                reminder_df = reminder_df[reminder_df['completed'].fillna(False).astype(bool) == False]
            
            reminders_list = reminder_df.to_dict('records')
            
            # Calculate stats
            urgent_reminders = len(reminder_df[reminder_df.get('urgency', '') == 'high'])
            
            # Count upcoming reminders (this week)
            upcoming_reminders = len(reminder_df)
            
            return render_template('reminders.html',
                                 reminders=reminders_list,
                                 urgent_reminders=urgent_reminders,
                                 upcoming_reminders=upcoming_reminders)
        else:
            return render_template('reminders.html',
                                 reminders=[],
                                 urgent_reminders=0,
                                 upcoming_reminders=0)
    
    except Exception as e:
        print(f"Error loading reminders: {e}")
        return render_template('reminders.html',
                             reminders=[],
                             urgent_reminders=0,
                             upcoming_reminders=0)

@app.route('/spam')
@login_required
def spam():
    try:
        data_path = get_user_data_path(session['username'])
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            
            # Filter spam emails
            spam_df = df[df['spam'].astype(str).str.lower() == 'true']
            spam_list = spam_df.to_dict('records')
            
            # Calculate stats
            total_emails = len(df)
            spam_count = len(spam_df)
            safe_emails = total_emails - spam_count
            spam_percentage = round((spam_count / total_emails * 100) if total_emails > 0 else 0, 1)
            
            return render_template('spam.html',
                                 spam_emails=spam_list,
                                 safe_emails=safe_emails,
                                 spam_percentage=spam_percentage)
        else:
            return render_template('spam.html',
                                 spam_emails=[],
                                 safe_emails=0,
                                 spam_percentage=0)
    
    except Exception as e:
        print(f"Error loading spam: {e}")
        return render_template('spam.html',
                             spam_emails=[],
                             safe_emails=0,
                             spam_percentage=0)

@app.route('/api/refresh', methods=['POST'])
@login_required
def refresh_emails():
    try:
        username = session.get('username')
        print(f"Manual refresh triggered for {username}")
        run_pipeline_for_user(username)
        return redirect(request.referrer or url_for('index'))
    except Exception as e:
        print(f"Refresh error: {e}")
        return redirect(request.referrer or url_for('index'))

@app.route('/api/stats')
def get_stats():
    try:
        data_path = get_user_data_path(session.get('username'))
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            total = len(df)
            processed = len(df[df['spam'].notna()])
        else:
            total = 0
            processed = 0
        
        return jsonify({
            'total_emails': total,
            'processed_today': processed,
            'last_update': pipeline_state['last_update'].strftime('%H:%M:%S') if pipeline_state['last_update'] else '--:--',
            'pipeline_running': pipeline_state['running']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/emails')
def get_emails():
    try:
        data_path = get_user_data_path(session.get('username'))
        if os.path.exists(data_path):
            df = pd.read_excel(data_path)
            emails = df.to_dict('records')
            return jsonify({'emails': emails})
        else:
            return jsonify({'emails': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/send_email', methods=['POST', 'GET'])
@login_required
def send_email():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
            
        username = session.get('username')
        recipient = data.get('recipient')
        subject = data.get('subject')
        body = data.get('body')
        
        token_path = get_user_token_path(username)
        if not os.path.exists(token_path):
            return jsonify({'success': False, 'message': 'Gmail account not connected. Please authorize first.'}), 401
            
        # Load credentials
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        # Refresh if necessary
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
        
        # Build Gmail service
        service = build('gmail', 'v1', credentials=creds)
        
        # Create message
        message = MIMEText(body)
        message['to'] = recipient
        message['subject'] = subject
        
        # Raw encoding
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send via Gmail API
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        
        # Log to file
        log_file = "sent_emails.xlsx"
        email_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'sender': username,
            'recipient': recipient,
            'subject': subject,
            'body': body,
            'status': 'sent'
        }
        
        if os.path.exists(log_file):
            df = pd.read_excel(log_file, engine="openpyxl")
            df = pd.concat([df, pd.DataFrame([email_data])], ignore_index=True)
        else:
            df = pd.DataFrame([email_data])
        
        df.to_excel(log_file, index=False)
        
        print(f"[EMAIL SENT VIA API] From: {username}, To: {recipient}, Subject: {subject}")
        
        return jsonify({'success': True, 'message': 'Email sent and logged successfully'})
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error sending email via API: {e}\n{error_details}")
        return jsonify({'success': False, 'message': f"Failed to send: {str(e)}"}), 500

@app.route('/api/summarize', methods=['POST'])
@login_required
def summarize_email():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        body = data.get('body')
        
        prompt = f"""Summarize this email concisely in 2-3 bullet points:
        
{body}"""
        
        response = generate_with_rotation("models/gemini-2.0-flash", prompt)
        
        return jsonify({
            'success': True,
            'summary': response.text
        })
    except Exception as e:
        print(f"Error summarizing: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/clean_text', methods=['POST'])
@login_required
def clean_text():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        body = data.get('body')
        
        prompt = f"""Extract only the main natural language text from this email suitable for reading aloud. 
        Remove all URLs, 'View image', 'Follow link', 'Caption', repetitive dashes/dividers, header/footer navigation, and technical metadata.
        Format it as clean, readable paragraphs.
        
        Email Content:
        {body}"""
        
        response = generate_with_rotation("models/gemini-2.0-flash", prompt)
        
        return jsonify({
            'success': True,
            'cleaned_text': response.text
        })
    except Exception as e:
        print(f"Error cleaning text: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/generate_ai_email', methods=['POST'])
def generate_ai_email():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        email_type = data.get('email_type')
        purpose = data.get('purpose')
        
        # Create prompt for Gemini
        prompt = f"""Generate a {email_type} email based on the following purpose:

{purpose}

Please write a professional, well-structured email. Include appropriate greeting, body, and closing."""
        
        response = generate_with_rotation("models/gemini-2.0-flash", prompt)
        
        generated_email = response.text
        
        # Log the generation
        log_file = "ai_generated_emails.xlsx"
        
        log_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'email_type': email_type,
            'purpose': purpose,
            'generated_email': generated_email
        }
        
        if os.path.exists(log_file):
            df = pd.read_excel(log_file)
            df = pd.concat([df, pd.DataFrame([log_data])], ignore_index=True)
        else:
            df = pd.DataFrame([log_data])
        
        df.to_excel(log_file, index=False)
        
        print(f"[AI EMAIL GENERATED] Type: {email_type}")
        
        return jsonify({
            'success': True,
            'email': generated_email
        })
    
    except Exception as e:
        print(f"Error generating AI email: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/generate_todo', methods=['POST'])
def generate_todo():
    try:
        data_path = get_user_data_path(session.get('username'))
        if not os.path.exists(data_path):
            return jsonify({'success': False, 'message': 'No emails found'}), 404
        
        df = pd.read_excel(data_path)
        
        # Filter reminders
        reminder_df = df[df['reminder'].notna() & (df['reminder'] != '')]
        
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Filter today's reminders (if date field exists)
        today_reminders = []
        for _, row in reminder_df.iterrows():
            date_str = str(row.get('date', ''))
            if today in date_str or date_str == 'none' or pd.isna(row.get('date')):
                today_reminders.append({
                    'reminder': row['reminder'],
                    'urgency': row.get('urgency', 'low'),
                    'category': row.get('category', 'Other'),
                    'from': row.get('from', 'Unknown')
                })
        
        if not today_reminders:
            return jsonify({'success': False, 'message': 'No reminders for today'}), 404
        
        # Create prompt for AI enhancement
        reminders_text = "\n".join([f"- {r['reminder']} (Urgency: {r['urgency']}, Category: {r['category']})" 
                                    for r in today_reminders])
        
        prompt = f"""Based on these email reminders, create a prioritized to-do list:

{reminders_text}

Please organize them by priority, add estimated time for each task, and suggest the best order to complete them. Format as a clear, actionable to-do list."""
        
        response = generate_with_rotation("models/gemini-2.0-flash", prompt)
        
        ai_todo_list = response.text
        
        # Create Excel file with to-do list
        filename = f"todo_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        todo_data = []
        for i, reminder in enumerate(today_reminders, 1):
            todo_data.append({
                'Task #': i,
                'Task': reminder['reminder'],
                'Urgency': reminder['urgency'],
                'Category': reminder['category'],
                'Source': reminder['from'],
                'Status': 'Pending'
            })
        
        # Add AI suggestions as a separate sheet
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            pd.DataFrame(todo_data).to_excel(writer, sheet_name='Tasks', index=False)
            pd.DataFrame([{'AI Suggestions': ai_todo_list}]).to_excel(writer, sheet_name='AI Suggestions', index=False)
        
        print(f"[TO-DO LIST GENERATED] File: {filename}, Tasks: {len(today_reminders)}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'task_count': len(today_reminders),
            'tasks': todo_data,
            'ai_todo': ai_todo_list
        })
    
    except Exception as e:
        print(f"Error generating to-do list: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/mark_complete', methods=['POST'])
def mark_complete():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        email_id = data.get('email_id')
        
        data_path = get_user_data_path(session.get('username'))
        if not os.path.exists(data_path):
            return jsonify({'success': False, 'message': 'Email file not found'}), 404
        
        df = pd.read_excel(data_path)
        
        # Add completed column if it doesn't exist
        if 'completed' not in df.columns:
            df['completed'] = False
        
        # Mark as complete
        df.loc[df['id'] == email_id, 'completed'] = True
        df.loc[df['id'] == email_id, 'completed_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        df.to_excel(data_path, index=False)
        
        print(f"[REMINDER COMPLETED] ID: {email_id}")
        
        return jsonify({'success': True, 'message': 'Reminder marked as complete'})
    
    except Exception as e:
        print(f"Error marking complete: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_from_directory('.', filename, as_attachment=True)
    except Exception as e:
        print(f"Error downloading file: {e}")
        return "File not found", 404

def main():
    pipeline_thread = threading.Thread(target=pipeline_loop, daemon=True)
    pipeline_thread.start()
    
    print("=" * 60)
    print("Email Pipeline Dashboard Starting")
    print("=" * 60)
    print(f"Dashboard URL: http://localhost:5000")
    print(f"Routes available:")
    print(f"  - / (Inbox)")
    print(f"  - /analysis (Email Analysis)")
    print(f"  - /reminders (Reminders & To-Do)")
    print(f"  - /spam (Spam Filter)")
    print(f"API Endpoints:")
    print(f"  - /api/send_email (Log sent emails)")
    print(f"  - /api/generate_ai_email (Generate AI emails)")
    print(f"  - /api/generate_todo (Generate to-do list)")
    print(f"Pipeline interval: 10 minutes")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

if __name__ == "__main__":
    main()