import pandas as pd
import requests
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_groq_key():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("WARNING: Missing GROQ_API_KEY in .env file!")
    return key

def batch_extract_data(emails_batch, custom_categories=None, max_retries=3):
    api_key = get_groq_key()
    last_error = "No GROQ_API_KEY configured"
    
    if not api_key:
        return None
        
    categories_str = ", ".join(custom_categories) if custom_categories else "Work, Education, Finance, Promotions, Personal, Support, Updates, Spam, Other"
    
    prompt = f"""You are an expert email parsing assistant. Your ONLY job is to analyze the following batch of emails and return a structured JSON response.

For EACH email, extract the following JSON fields EXACTLY as named:
- "spam" (string "true" or "false")
- "reminder" (string: a SPECIFIC actionable task the user must do, or "" if none. IMPORTANT: Only create reminders for emails that genuinely require the user to take action — e.g. reply to someone, attend a meeting, pay a bill, submit a form. Do NOT create reminders for newsletters, promotional offers, automated notifications, social media updates, shipping updates with no action needed, or informational emails. Use "" for those.)
- "reminder_date" (string, YYYY-MM-DD or "")
- "category" (string: one of {categories_str})
- "sentiment" (string, tone of email)
- "urgency" (string: "high", "low", "moderate")

Input Emails:
"""
    
    for i, em in enumerate(emails_batch):
        subject_str = str(em['subject'])[:200] if pd.notna(em['subject']) else ""
        body_str = str(em['body'])[:1000] if pd.notna(em['body']) else ""
        prompt += f"--- Email {i+1} ---\nSubject: {subject_str}\nBody: {body_str}\n\n"

    prompt += "\nOutput ONLY valid JSON containing a single key 'results' which holds an array of objects (one for each email in exact order)."

    for attempt in range(max_retries):
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
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code == 200:
                out = response.json()["choices"][0]["message"]["content"]
                try:
                    data = json.loads(out)
                    if "results" in data and isinstance(data["results"], list):
                        return data["results"]
                except json.JSONDecodeError:
                    last_error = "Groq did not return formatted JSON"
                    time.sleep(2)
                    continue
            else:
                last_error = f"HTTP Error {response.status_code}: {response.text}"
                if response.status_code == 429:
                    print("Groq rate limit hit. Sleeping 10s...")
                    time.sleep(10)
                else:
                    time.sleep(2)
        except Exception as e:
            error_msg = str(e)
            last_error = error_msg
            print(f"Groq API failed. Error: {error_msg}")
            time.sleep(5)
            
    print(f"All retries failed in batch_extract_data: {last_error}")
    return None

def run_function_call(df, custom_categories=None):
    cols=["spam", "reminder", "reminder_date", "category", "sentiment", "urgency"]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)
    
    def is_new(val):
        return pd.isna(val) or str(val).strip() == ""
    
    new_rows = df[df["spam"].apply(is_new)]
    
    if not new_rows.empty:
        print(f"Processing {len(new_rows)} new emails for AI analysis using Groq BATCHING...")
        
    CHUNK_SIZE = 25  # Process 25 emails at once
    indices = new_rows.index.tolist()
    
    for i in range(0, len(indices), CHUNK_SIZE):
        batch_indices = indices[i:i + CHUNK_SIZE]
        batch_emails = []
        for idx in batch_indices:
            batch_emails.append({
                "subject": df.at[idx, "subject"],
                "body": df.at[idx, "body"]
            })
            
        print(f"Sending batch of {len(batch_emails)} emails to Groq...")
        results = batch_extract_data(batch_emails, custom_categories=custom_categories)
        
        if results and len(results) == len(batch_emails):
            for result_idx, result in enumerate(results):
                df_idx = batch_indices[result_idx]
                for key, value in result.items():
                    if key in cols:
                        df.at[df_idx, key] = str(value)
        else:
            print(f"Warning: Batch returned mismatched results. Expected {len(batch_emails)}.")
            
        time.sleep(2) # Friendly delay
        
    return df