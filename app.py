import os
import json
import spacy
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq

from prompts import SYSTEM_PROMPT, CHAT_PROMPT

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
nlp = spacy.load("en_core_web_sm")

MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.3


def add_line_numbers(text):
    lines = text.split("\n")
    return "\n".join(f"[Line {i+1}] {line}" for i, line in enumerate(lines))


def redact_pii(text):
    doc = nlp(text)
    redacted = text
    # process in reverse so character offsets don't shift as replacements happen
    for ent in reversed(doc.ents):
        if ent.label_ == "PERSON" and len(ent.text.split()) < 2:
            continue  # skip likely false positives (single capitalized words)
        if ent.label_ in ("PERSON", "GPE", "ORG", "LOC", "NORP"):
            placeholder = f"[REDACTED_{ent.label_}]"
            redacted = redacted[:ent.start_char] + placeholder + redacted[ent.end_char:]
    return redacted


def prepare_case(case_text):
    """Redact PII first, then number lines. Every LLM call goes through this."""
    redacted = redact_pii(case_text)
    return redacted, add_line_numbers(redacted)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    case_text = request.form.get("case_text", "")
    if not case_text.strip():
        return jsonify({"error": "No case text provided"}), 400

    redacted_text, numbered_text = prepare_case(case_text)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Here is the case file:\n\n{numbered_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
        )
    except Exception as e:
        print("Groq error:", e)
        return jsonify({"error": "Model call failed (possibly rate limited). Wait a few seconds and retry."}), 502

    raw = response.choices[0].message.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return jsonify({"error": "Model returned invalid JSON. Try again."}), 500

    print("=== PARSED GUIDELINES ===")  # remove before demo
    print(json.dumps(parsed, indent=2))

    return jsonify({"guidelines": parsed.get("guidelines", []), "redacted_input": redacted_text})


@app.route("/chat", methods=["POST"])
def chat():
    case_text = request.form.get("case_text", "")
    question = request.form.get("question", "")
    history = json.loads(request.form.get("history", "[]"))

    if not case_text.strip() or not question.strip():
        return jsonify({"error": "Missing case text or question"}), 400

    _, numbered_text = prepare_case(case_text)

    messages = [{"role": "system", "content": CHAT_PROMPT.format(case_file=numbered_text)}]
    for turn in history:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
        )
    except Exception as e:
        print("Groq error:", e)
        return jsonify({"error": "Model call failed (possibly rate limited). Wait a few seconds and retry."}), 502

    return jsonify({"answer": response.choices[0].message.content})


if __name__ == "__main__":
    app.run(debug=True, port=5000)