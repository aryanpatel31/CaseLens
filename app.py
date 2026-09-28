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
A - Allegiance to the United States: Concern is involvement in or support of sabotage, espionage, terrorism, treason, or efforts to overthrow the U.S. government by unconstitutional means.
B - Foreign Influence: Foreign contacts or interests (family, friends, financial ties) that create a risk of exploitation, pressure, or coercion, or a conflict between the person's loyalties. Risk depends on the country, the closeness of the relationship, and any ties to foreign governments or intelligence services.
C - Foreign Preference: Acting in ways that show a preference for a foreign country over the U.S., such as exercising foreign citizenship, holding a foreign passport, foreign military service, or employment by a foreign government.
D - Sexual Behavior: Sexual conduct that is criminal, compulsive, or high-risk, or that shows poor judgment or creates vulnerability to coercion or blackmail.
E - Personal Conduct: Dishonesty, rule-breaking, or questionable judgment. Includes deliberate omission or falsification on security forms, refusing to cooperate with the investigation, and conduct that creates vulnerability to exploitation.
F - Financial Considerations: Unpaid debts, financial irresponsibility, unexplained affluence, or inability to live within one's means, which may indicate risk of illegal acts to generate funds. Also includes fraud, embezzlement, and failure to file or pay taxes.
G - Alcohol Consumption: Excessive alcohol use that leads to questionable judgment or unreliability, such as DUIs, work incidents, binge drinking, or diagnosed alcohol use disorder.
H - Drug Involvement and Substance Misuse: Illegal drug use, misuse of prescription drugs, drug possession or distribution, or failure to follow treatment.
I - Psychological Conditions: Emotional, mental, or personality conditions that may impair judgment, reliability, or trustworthiness, as assessed by a qualified professional. Seeking mental health counseling is not itself a concern.
J - Criminal Conduct: Criminal activity, arrests, or convictions that raise doubt about judgment, reliability, or trustworthiness. Patterns and recency matter.
K - Handling Protected Information: Deliberate or negligent failure to follow rules for protecting classified or sensitive information, including security violations.
L - Outside Activities: Outside employment or activities (such as work for a foreign government, foreign business, or certain organizations) that could conflict with security responsibilities or risk unauthorized disclosure.
M - Use of Information Technology: Failure to comply with rules for protecting IT systems, including unauthorized access, modifying systems, introducing unauthorized software, or misusing systems.
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

Risk levels — apply these definitions strictly and consistently:
- "green": No information relevant to this guideline exists in the case file, OR the information present raises no concern and requires no follow-up.
- "yellow": Relevant information exists, but it is incomplete, unverified, or requires clarification before an adjudicator could assess it. Use yellow whenever documentation is missing or a claim is self-reported without independent verification, even if the underlying facts (once verified) might turn out to be fine.
- "red": The information itself — even if fully verified as stated — would constitute a specific documented concern under this guideline (e.g., unpaid debt exceeding $10,000 with no resolution plan, direct evidence of foreign government employment, undisclosed criminal conviction, deliberate omission of information on the SF-86).

Important: unverified or undocumented claims should be "yellow," not "red," unless the underlying fact pattern itself is inherently concerning regardless of verification status.

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
        response_format={"type": "json_object"},
        temperature=0.3
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