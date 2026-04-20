import os, base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email
import pandas as pd

# Gmail Fetch Core Logic

def saveToExcel(df, filepath):
    df.to_excel(filepath, index=False)
    print(f"Emails saved to {filepath}")

def list_messages(service, q=None, label_ids=None, max_results=500):
    """Fetch all messages matching the query, paginating through all results."""
    all_messages = []
    page_token = None
    while True:
        response = service.users().messages().list(
            userId='me', q=q, labelIds=label_ids,
            maxResults=max_results, pageToken=page_token
        ).execute()
        all_messages.extend(response.get('messages', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return all_messages

def get_message(service, msg_id):
    return service.users().messages().get(userId='me', id=msg_id, format='full').execute()

def get_payload_text(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            text = get_payload_text(part)
            if text:
                return text
    else:
        mime_type = payload.get('mimeType', '')
        body = payload.get('body', {}).get('data')
        if body:
            data = base64.urlsafe_b64decode(body.encode('UTF-8'))
            if mime_type == 'text/plain' or mime_type.startswith('text/'):
                return data.decode('utf-8', errors='replace')
            else:
                return data.decode('utf-8', errors='replace')
    return None

def download_attachments(service, msg):
    parts = msg.get('payload', {}).get('parts', [])
    for p in parts:
        filename = p.get('filename')
        body = p.get('body', {})
        if filename:
            att_id = body.get('attachmentId')
            if att_id:
                try:
                    att = service.users().messages().attachments().get(
                        userId='me', messageId=msg['id'], id=att_id
                    ).execute()
                    data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
                    with open(filename, 'wb') as f:
                        f.write(data)
                    print('Saved attachment', filename)
                except Exception as e:
                    print(f"Error downloading attachment {filename}: {e}")

def load_existingEmails(filepath):
    if os.path.exists(filepath):
        return pd.read_excel(filepath, engine="openpyxl")
    else:
        return pd.DataFrame(columns=["id", "date", "from", "subject", "body"])

def main(creds=None, filepath="email.xlsx"):
    if not creds:
        print("Error: No credentials provided to main")
        return
        
    service = build('gmail', 'v1', credentials=creds)
    msgs = list_messages(service, q='in:inbox', label_ids=None)
    print(f'Found {len(msgs)} messages')
    new_emails = []
    existing_df = load_existingEmails(filepath)
    
    # Create a mapping of id to date for quick lookup
    id_to_date = {str(row['id']): str(row.get('date', '')) for _, row in existing_df.iterrows()}
    
    for m in msgs:
        msg_id = str(m["id"])
        if msg_id in id_to_date:
            existing_date = id_to_date[msg_id]
            if existing_date and existing_date not in ["", "nan", "No Date", "n/a"]:
                continue
        
        try:
            msg = get_message(service, m['id'])
            headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            text = get_payload_text(msg['payload'])
            
            # download attachments if any
            download_attachments(service, msg)
            
            new_emails.append({
                "id" : m["id"],
                "date" : headers.get("Date", "n/a"),
                "from" : headers.get("From", "n/a"),
                "subject" : headers.get("Subject", "n/a"),
                "body" : text
            })
        except Exception as e:
            print(f"Error fetching message {m['id']}: {e}")

    if new_emails:
        df=pd.concat([existing_df, pd.DataFrame(new_emails)], ignore_index=True)
        # Keep the record with the most data (re-fetched date) if duplicates exist
        df.drop_duplicates(subset=['id'], keep='last', inplace=True)
        saveToExcel(df, filepath)
