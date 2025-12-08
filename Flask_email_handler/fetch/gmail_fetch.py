import os, base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email
import pandas as pd

# If modifying scopes, delete token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']  # read-only; change if needed
FILEPATH = "email.xlsx"

def saveToExcel(df):
    df.to_excel(FILEPATH)
    print("Emails saved")

def auth():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return creds

def list_messages(service, q=None, label_ids=None, max_results=10):
    response = service.users().messages().list(userId='me', q=q, labelIds=label_ids, maxResults=max_results).execute()
    return response.get('messages', [])

def get_message(service, msg_id):
    return service.users().messages().get(userId='me', id=msg_id, format='full').execute()

def get_payload_text(payload):
    # Recursive walk to find text/plain or base64 body
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
                # Return raw for other types
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
                att = service.users().messages().attachments().get(
                    userId='me', messageId=msg['id'], id=att_id
                ).execute()
                data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
                with open(filename, 'wb') as f:
                    f.write(data)
                print('Saved attachment', filename)
def load_existingEmails():
    if os.path.exists(FILEPATH):
        return pd.read_excel(FILEPATH)
    else:
        return pd.DataFrame(columns=["id", "date", "from", "subject", "body"])

def main():
    creds = auth()
    service = build('gmail', 'v1', credentials=creds)
    msgs = list_messages(service, q='is:unread', label_ids=None)
    print(f'Found {len(msgs)} messages')
    new_emails = []
    existing_df = load_existingEmails()
    existing_IDs = set(existing_df["id"].astype(str))
    for m in msgs:
        if m["id"] in existing_IDs:
            print(f"skipping message ID {m['id']}")
            continue
        msg = get_message(service, m['id'])
        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        print('From:', headers.get('From'))
        print('Subject:', headers.get('Subject'))
        text = get_payload_text(msg['payload'])
        print('Body preview:', (text or '')[:400])
        # download attachments if any
        download_attachments(service, msg)
        new_emails.append({
            "id" : m["id"],
            "date" : headers.get("Date", "n/a"),
            "from" : headers.get("From", "n/a"),
            "subject" : headers.get("Subject", "n/a"),
            "body" : text
        })
    if new_emails:
        df=pd.concat([existing_df, pd.DataFrame(new_emails)], ignore_index=True)
        saveToExcel(df)


if __name__ == '__main__':
    main()