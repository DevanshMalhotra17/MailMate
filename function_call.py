import google.generativeai as genai
import pandas as pd
import time
import os
API_KEY = "AIzaSyCzv_m9tL7SfqkekHaWQSl9SHRc8cM0bMM"
genai.configure(api_key=API_KEY)

functions = [
    {
        "name" : "create_email_analysis",
        "description" : "analyze an email and decide if it needs a reminder. Return the reminder text, date, category, sentiment, urgency and check if it is spam.",
        "parameters" : {"type": "object", 
                        "properties": {
                            "reminder": {
                                "type": "string",
                                "description": "text of reminder"
                            },
                                "date" : {
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
                        "required" : ["reminder", "date", "category", "sentiment", "urgency", "spam"]
        }
    }
]

def extract_data(subject, body):
    model = genai.GenerativeModel(model_name="gemini-2.5-flash", tools = [
        {
            "function_declarations": functions
        }
    ])
    prompt = f"""annalyze the email and create and call the create_reminder with a reminder and a date if needed
    subject:{subject}, body:{body}"""
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
                            "date": args["date"] if "date" in args else "",
                            "category": args["category"] if "category" in args else "Other",
                                    "sentiment": args["sentiment"] if "sentiment" in args else "Neutral",
                                    "urgency": args["urgency"] if "urgency" in args else "Low",
                                }    
    except Exception as e:
        print("error", e)
    return None

# # reminder, date, category, sentiment, urgency, spam = extract_data(subject, body)
# print(reminder)
# print(date)
# print(category)
# print(sentiment)
# print(urgency)
# data = {
#     "reminder": reminder,
#     "date": date,
#     "category": category,
#     "sentiment": sentiment,
#     "urgency": urgency,
#     "spam": spam
# }
# df = pd.DataFrame([data])
# df.to_csv("email_data.xlsx")
def run_function_call(df):
    cols=["spam", "reminder", "date", "category", "sentiment", "urgency"]
    for col in cols:
        if col not in df:
            df[col]=None
    new_rows=df[df["spam"].isna()]
    for idx,row in new_rows.iterrows():
        result=extract_data(row["subject"], row["body"])
        if result:
            for key, value in result.items():
                df.at[idx,key]=value
    return df