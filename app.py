import os
import json
import spacy
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq

from prompts import SYSTEM_PROMPT, CHAT_PROMPT, RECONCILER_PROMPT, VERIFIER_PROMPT

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


def prepare_case(files):
    """
    files: list of {"name": ..., "text": ...}
    Returns: (combined_redacted_text_for_display, numbered_text_for_llm)
    Each file is redacted individually, then joined with clear boundary markers.
    Line numbers are continuous across the whole combined text so citations stay simple.
    """
    combined_parts = []
    for f in files:
        redacted = redact_pii(f["text"])
        combined_parts.append(f"=== FILE: {f['name']} ===\n{redacted}")

    combined_text = "\n\n".join(combined_parts)
    numbered_text = add_line_numbers(combined_text)
    return combined_text, numbered_text


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    files = data.get("files", [])

    if not files:
        return jsonify({"error": "No files provided"}), 400

    combined_text, numbered_text = prepare_case(files)

    # Agent 1: Analyst
    try:
        analyst_response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Here is the case file:\n\n{numbered_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
        )
        analyst_result = json.loads(analyst_response.choices[0].message.content)
    except Exception as e:
        print("Analyst agent error:", e)
        return jsonify({"error": "Analysis failed (possibly rate limited). Please retry."}), 502

    contradictions = []
    # Agent 2: Reconciler (only worth running with 2+ files)
    if len(files) > 1:
        try:
            reconciler_response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": RECONCILER_PROMPT},
                    {"role": "user", "content": (
                        f"Analyst's guideline findings (for context only):\n{json.dumps(analyst_result)}\n\n"
                        f"Case file:\n\n{numbered_text}"
                    )},
                ],
                response_format={"type": "json_object"},
                temperature=TEMPERATURE,
            )
            reconciler_result = json.loads(reconciler_response.choices[0].message.content)
            contradictions = reconciler_result.get("contradictions", [])
        except Exception as e:
            print("Reconciler agent error (non-fatal, continuing without contradictions):", e)

    # Agent 3: Verifier
    verification_flags = []
    try:
        verifier_response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": VERIFIER_PROMPT},
                {"role": "user", "content": (
                    f"Case file:\n\n{numbered_text}\n\n"
                    f"Analysis to verify:\n{json.dumps(analyst_result.get('guidelines', []))}"
                )},
            ],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
        )
        verifier_result = json.loads(verifier_response.choices[0].message.content)
        verification_flags = verifier_result.get("flags", [])
    except Exception as e:
        print("Verifier agent error (non-fatal, continuing without verification):", e)

    return jsonify({
        "guidelines": analyst_result.get("guidelines", []),
        "contradictions": contradictions,
        "verification_flags": verification_flags,
        "combined_text": combined_text
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    files = data.get("files", [])
    question = data.get("question", "")
    history = data.get("history", [])

    if not files or not question.strip():
        return jsonify({"error": "Missing case files or question"}), 400

    _, numbered_text = prepare_case(files)

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
        print("Chat agent error:", e)
        return jsonify({"error": "Model call failed (possibly rate limited). Wait a few seconds and retry."}), 502

    return jsonify({"answer": response.choices[0].message.content})

if __name__ == "__main__":
    app.run(debug=True, port=5001)