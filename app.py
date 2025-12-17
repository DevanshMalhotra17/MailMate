from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app=Flask(__name__)

@app.route("/")
def home():
    df=pd.read_excel("email.xlsx", engine="openpyxl")
    emails=df.to_dict(orient="records")
    return render_template("index.html", emails=emails)

if __name__=="__main__":
    app.run(debug=True)