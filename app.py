import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    case_text = request.form.get("case_text", "")

    if not case_text.strip():
        return jsonify({"error": "No case text provided"}), 400

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Summarize this text in one sentence:\n\n{case_text}"}
        ]
    )

    result = response.choices[0].message.content
    return jsonify({"result": result})

if __name__ == "__main__":
    app.run(debug=True, port=5000)