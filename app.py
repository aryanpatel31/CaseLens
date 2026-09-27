import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq
import spacy
import json

nlp = spacy.load("en_core_web_sm")

def add_line_numbers(text):
    lines = text.split("\n")
    numbered = "\n".join(f"[Line {i+1}] {line}" for i, line in enumerate(lines))
    return numbered

def redact_pii(text):
    doc = nlp(text)
    redacted = text
    # process in reverse so character offsets don't shift as replacement happens
    for ent in reversed(doc.ents):
        if ent.label_ == "PERSON" and len(ent.text.split()) < 2:
            continue  # skip likely false positives (single capitalized words)
        if ent.label_ in ("PERSON", "GPE", "ORG", "LOC", "NORP"):
            placeholder = f"[REDACTED_{ent.label_}]"
            redacted = redacted[:ent.start_char] + placeholder + redacted[ent.end_char:]
    return redacted

load_dotenv()

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.route("/")
def home():
    return render_template("index.html")

GUIDELINES = """
A - Allegiance to the United States
B - Foreign Influence
C - Foreign Preference
D - Sexual Behavior
E - Personal Conduct
F - Financial Considerations
G - Alcohol Consumption
H - Drug Involvement and Substance Misuse
I - Psychological Conditions
J - Criminal Conduct
K - Handling Protected Information
L - Outside Activities
M - Use of Information Technology
"""

SYSTEM_PROMPT = f"""You are an assistant that helps security clearance adjudicators organize case file information. You do NOT make approve/deny recommendations. The case file text you receive will have line numbers in brackets like [Line 5] at the start of each line.

Your job is to analyze the case against these adjudicative guidelines:
{GUIDELINES}

For EACH of the 13 guidelines, output an assessment — even if there's no relevant information (mark those as "green" with evidence "No relevant information found").

Respond ONLY with valid JSON in this exact structure, no other text before or after:

{{
  "guidelines": [
    {{
      "letter": "A",
      "name": "Allegiance to the United States",
      "risk": "green",
      "evidence": "string describing what the case file says, or 'No relevant information found'",
      "unclear": "string describing what's missing/unverified, or empty string if none",
      "followup": "a specific follow-up question, or empty string if none",
      "citations": "line numbers referenced, e.g. 'Lines 9-10', or empty string"
    }}
  ]
}}

Risk levels:
- "green": no concern, or no relevant information
- "yellow": some relevant information exists but is unclear, unverified, or needs follow-up
- "red": significant concern that clearly implicates the guideline (e.g., large undisclosed debt, unverified foreign government ties, deceptive conduct)

Include all 13 guidelines in the array, in order A through M. Respond with ONLY the JSON object, nothing else."""

@app.route("/analyze", methods=["POST"])
def analyze():
    case_text = request.form.get("case_text", "")

    if not case_text.strip():
        return jsonify({"error": "No case text provided"}), 400

    redacted_text = redact_pii(case_text)
    numbered_text = add_line_numbers(redacted_text)

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the case file:\n\n{numbered_text}"}
        ],
        response_format={"type": "json_object"}
    )

    raw = response.choices[0].message.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse model output", "raw": raw}), 500

    print("=== PARSED GUIDELINES ===")
    print(json.dumps(parsed, indent=2))
    print("=====================")
    return jsonify({"guidelines": parsed.get("guidelines", []), "redacted_input": redacted_text})

@app.route("/chat", methods=["POST"])
def chat():
    case_text = request.form.get("case_text", "")
    question = request.form.get("question", "")
    history = request.form.get("history", "[]")  # JSON string of prior Q&A pairs

    import json
    history_list = json.loads(history)

    if not case_text.strip() or not question.strip():
        return jsonify({"error": "Missing case text or question"}), 400

    redacted_text = redact_pii(case_text)
    numbered_text = add_line_numbers(redacted_text)

    chat_system_prompt = f"""You are an assistant helping a security clearance adjudicator review a case file. The case file below has line numbers in brackets. Answer the adjudicator's questions based ONLY on the information in the case file. If the case file doesn't contain the answer, say so clearly — do not guess or make up information. Cite line numbers when relevant. Do not make approve/deny recommendations.
                            CASE FILE:
                            {numbered_text}"""

    messages = [{"role": "system", "content": chat_system_prompt}]
    for turn in history_list:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages
    )

    answer = response.choices[0].message.content
    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(debug=True, port=5000)