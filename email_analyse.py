import google.generativeai as genai
import pandas as pd
import time
import os

# Configure API key correctly
genai.configure(api_key=os.getenv("API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

def classify_email(subject, body):
    prompt = f"""
    You are a spam email analyzer.
    Classify the following email as spam or not spam.
    Respond only with "True" (spam) or "False" (not spam).

    Subject: {subject}
    Body: {body}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip().lower()
        if "true" in text:
            return True
        elif "false" in text:
            return False
    except Exception as e:
        print("Error:", e)
    return False

# Load data
df = pd.read_excel("email.xlsx")

spam_results = []
for _, row in df.iterrows():
    subject = str(row.get("subject", ""))
    body = str(row.get("body", ""))
    is_spam = classify_email(subject, body)
    spam_results.append(is_spam)
    time.sleep(1)  # to avoid rate limits

df["spam"] = spam_results
df.to_excel("email_check.xlsx", index=False)
print("Spam filter completed successfully.")