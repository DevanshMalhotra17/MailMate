from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import pandas as pd

df = pd.read_excel("email.xlsx")

analyzer = SentimentIntensityAnalyzer()

def get_sentiment(text):
    if not isinstance(text, str) or not text.strip():
        return 0.0
    return analyzer.polarity_scores(text)["compound"]

def get_sentiment_label(score):
    if score > 0.05:
        return "Positive"
    elif score < -0.05:
        return "Negative"
    else:
        return "Neutral"

df["sentimentScore"] = df["body"].apply(get_sentiment)
df["sentimentLabel"] = df["sentimentScore"].apply(get_sentiment_label)

df.to_excel("email.xlsx", index=False)