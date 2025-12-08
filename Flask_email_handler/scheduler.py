import time
import threading
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, send_from_directory
import pandas as pd
from fetch.gmail_fetch import main as fetch_gmail
from function_call import run_function_call
from collections import Counter
import google.generativeai as genai
from flask_mail import Mail, Message

app = Flask(__name__, template_folder="templates")
base_dir = os.path.dirname(os.path.abspath(__file__))
app.config["MAIL_SERVER"]="smtp.gmail.com"
app.config["MAIL_PORT"]=587
app.config["MAIL_USE_TLS"]=True
app.config["MAIL_USE_SSL"]=False
app.config["MAIL_USERNAME"]="devansh.malhotra2027@gmail.com"
app.config["MAIL_PASSWORD"]="oupe afur cgeh xrio"
app.config["MAIL_DEFAULT_SENDER"]=("MyApp", "devansh.malhotra2027@gmail.com")
mail=Mail(app)

# Configure Gemini API
API_KEY = "AIzaSyCzv_m9tL7SfqkekHaWQSl9SHRc8cM0bMM"
genai.configure(api_key=API_KEY)

# Global state
pipeline_state = {
    'running': True,
    'last_update': None,
    'total_emails': 0,
    'processed_today': 0
}

# Serve CSS from templates folder
@app.route('/style.css')
def serve_css():
    return send_from_directory('templates', 'style.css', mimetype='text/css')

def run_pipeline():
    """Run the email fetching and processing pipeline"""
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running pipeline...")
        
        # Fetch emails from Gmail
        fetch_gmail()
        
        # Read and process emails
        df = pd.read_excel("email.xlsx")
        df = run_function_call(df)
        
        # Save processed emails
        df.to_excel("email.xlsx", index=False)
        
        # Update state
        pipeline_state['last_update'] = datetime.now()
        pipeline_state['total_emails'] = len(df)
        pipeline_state['processed_today'] = len(df[df.get('spam', '').notna()])
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline completed. Processed {len(df)} emails.")
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Pipeline error: {e}")

def pipeline_loop():
    """Background thread that runs the pipeline every 10 minutes"""
    while True:
        if pipeline_state['running']:
            run_pipeline()
        time.sleep(600)  # 10 minutes

@app.route('/')
def index():
    """Main dashboard page - Inbox view"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
            emails = df.to_dict('records')
        else:
            emails = []
        
        return render_template('index.html', emails=emails)
    
    except Exception as e:
        print(f"Error loading emails: {e}")
        return render_template('index.html', emails=[])

@app.route('/analysis')
def analysis():
    """Analysis page with charts and statistics"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
            
            # Calculate sentiment counts
            positive_count = len(df[df.get('sentiment', '').str.lower().str.contains('positive', na=False)])
            negative_count = len(df[df.get('sentiment', '').str.lower().str.contains('negative', na=False)])
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
            timeline_data = [5, 8, 6, 9, 7, 10, 12]  # Placeholder
            
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
def reminders():
    """Reminders page showing all emails with reminders"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
            
            # Filter emails that have reminders
            reminder_df = df[df['reminder'].notna() & (df['reminder'] != '')]
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
def spam():
    """Spam page showing all detected spam emails"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
            
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
def refresh_emails():
    """Manually trigger pipeline"""
    try:
        run_pipeline()
        return redirect(request.referrer or url_for('index'))
    except Exception as e:
        print(f"Error: {e}")
        return redirect(request.referrer or url_for('index'))

@app.route('/api/stats')
def get_stats():
    """API endpoint to get current statistics"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
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
    """API endpoint to get all emails as JSON"""
    try:
        if os.path.exists("email.xlsx"):
            df = pd.read_excel("email.xlsx")
            emails = df.to_dict('records')
            return jsonify({'emails': emails})
        else:
            return jsonify({'emails': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/send_email', methods=['POST'])
def send_email():
    """Log email sending data"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        recipient = data.get('recipient')
        subject = data.get('subject')
        body = data.get('body')
        print(recipient)
        msg=Message(
            subject=subject,
            recipients=[recipient],
            body=body
        )

        mail.send(msg)

        # Log to file
        log_file = "sent_emails.xlsx"
        
        email_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'recipient': recipient,
            'subject': subject,
            'body': body,
            'status': 'logged'
        }
        
        if os.path.exists(log_file):
            df = pd.read_excel(log_file)
            df = pd.concat([df, pd.DataFrame([email_data])], ignore_index=True)
        else:
            df = pd.DataFrame([email_data])
        
        df.to_excel(log_file, index=False)
        
        print(f"[EMAIL SENT] To: {recipient}, Subject: {subject}")
        
        return jsonify({'success': True, 'message': 'Email logged successfully'})
    
    except Exception as e:
        print(f"Error logging email: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/generate_ai_email', methods=['POST'])
def generate_ai_email():
    """Generate email using Gemini AI"""
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
        
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        
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
    """Generate AI-enhanced to-do list from today's reminders"""
    try:
        if not os.path.exists("email.xlsx"):
            return jsonify({'success': False, 'message': 'No emails found'}), 404
        
        df = pd.read_excel("email.xlsx")
        
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
        
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        
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
            'task_count': len(today_reminders)
        })
    
    except Exception as e:
        print(f"Error generating to-do list: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/mark_complete', methods=['POST'])
def mark_complete():
    """Mark a reminder as complete"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        email_id = data.get('email_id')
        
        if not os.path.exists("email.xlsx"):
            return jsonify({'success': False, 'message': 'Email file not found'}), 404
        
        df = pd.read_excel("email.xlsx")
        
        # Add completed column if it doesn't exist
        if 'completed' not in df.columns:
            df['completed'] = False
        
        # Mark as complete
        df.loc[df['id'] == email_id, 'completed'] = True
        df.loc[df['id'] == email_id, 'completed_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        df.to_excel("email.xlsx", index=False)
        
        print(f"[REMINDER COMPLETED] ID: {email_id}")
        
        return jsonify({'success': True, 'message': 'Reminder marked as complete'})
    
    except Exception as e:
        print(f"Error marking complete: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download generated files"""
    try:
        return send_from_directory('.', filename, as_attachment=True)
    except Exception as e:
        print(f"Error downloading file: {e}")
        return "File not found", 404

def main():
    """Main function to start Flask app and background pipeline"""
    # Start pipeline in background thread
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
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

if __name__ == "__main__":
    main()