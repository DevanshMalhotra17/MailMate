import google.generativeai as genai
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

functions = [
    {
        "name" : "create_email_analysis",
        "description" : "analyze an email and decide if it needs a reminder. Return the reminder text, date, category, sentiment, urgency and check if it is spam.",
        "parameters" : {"type": "object", 
                        "properties": {
                            "reminder": {
                                "type": "string",
                                "description": "text of reminder. If no reminder or action is needed, return exactly an empty string ''."
                            },
                            "reminder_date" : {
                                "type" : "string",
                                "description" : "date of the reminder in MM-DD-YYYY format or else just give none"
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "Work", "Education", "Finance", "Promotions", "Personal", "Support", "Updates", "Spam", "Other"
                                ],
                                "description": "category or type of the email" # give examples in the string if not accurate
                            },
                            "sentiment": {
                                "type": "string",
                                "description": "emotional tone of the email" # give examples in the string if not accurate
                            },
                            "urgency": {
                                "type": "string",
                                "enum": [
                                    "high", "low", "moderate"
                                ],
                                "description": "urgency of the email"
                            },
                            "spam": {
                                "type": "string",
                                "enum": [
                                    "true", "false"
                                ],
                                "description": "true if email is spam, false if email is not spam"
                            }
                        },
                        "required" : ["reminder", "reminder_date", "category", "sentiment", "urgency", "spam"]
        }
    }
]

def extract_data(subject, body):
    model = genai.GenerativeModel(model_name="models/gemini-1.5-flash", tools = [
        {
            "function_declarations": functions
        }
    ])
    prompt = f"""Analyze the email and call the create_email_analysis function with the extracted details. 
    IMPORTANT: If there is no clear task or reminder to be set, leave the 'reminder' field as an empty string. 
    Do not use placeholders like 'None' or 'No action'.
    
    Subject: {subject}
    Body: {body}"""
    try:
        response = model.generate_content(prompt)
        if response.candidates:
            parts = response.candidates[0].content.parts
            for part in parts:
                if "function_call" in part:
                    fn_call = part.function_call
                    args = fn_call.args
                    return {
                            "spam": args["spam"] if "spam" in args else False,
                            "reminder": args["reminder"] if "reminder" in args else "",
                            "reminder_date": args["reminder_date"] if "reminder_date" in args else "",
                            "category": args["category"] if "category" in args else "Other",
                                    "sentiment": args["sentiment"] if "sentiment" in args else "Neutral",
                                    "urgency": args["urgency"] if "urgency" in args else "Low",
                                }    
    except Exception as e:
        print("error", e)
    return None

def run_function_call(df):
    cols=["spam", "reminder", "reminder_date", "category", "sentiment", "urgency"]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)
    
    # Process rows where spam is missing or empty
    def is_new(val):
        return pd.isna(val) or str(val).strip() == ""
    
    new_rows = df[df["spam"].apply(is_new)]
    for idx,row in new_rows.iterrows():
        result=extract_data(row["subject"], row["body"])
        if result:
            for key, value in result.items():
                df.at[idx,key]=value
    return df