import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq
import spacy

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

Your job is to:

1. Read the case file text provided.
2. Identify which of the following adjudicative guidelines are relevant to information in the case:
{GUIDELINES}

3. For each relevant guideline, extract the specific evidence from the case file that relates to it, and cite the exact line number(s) where that evidence appears.
4. Note anything that is unclear, missing, or unverified.
5. Suggest one targeted follow-up question the adjudicator could ask to resolve each unclear item.

Format your response clearly with a section for each relevant guideline, like this:

## Guideline [Letter] - [Name]
**Evidence:** [what the case file says] (Line [X])
**Unclear/Missing:** [what's not documented or verified, if anything]
**Suggested Follow-up:** [a specific question, if applicable]

Only include guidelines that are actually relevant to the case file. Do not recommend approval or denial. Always cite line numbers for evidence you reference."""

@app.route("/analyze", methods=["POST"])
def analyze():
    case_text = request.form.get("case_text", "")

    if not case_text.strip():
        return jsonify({"error": "No case text provided"}), 400

    redacted_text = redact_pii(case_text)
    numbered_text = add_line_numbers(redacted_text)

    print("=== NUMBERED + REDACTED TEXT ===")
    print(numbered_text)
    print("=====================")

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the case file:\n\n{numbered_text}"}
        ]
    )

    result = response.choices[0].message.content
    return jsonify({"result": result, "redacted_input": redacted_text})

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