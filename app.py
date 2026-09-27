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

SYSTEM_PROMPT = f"""You are an assistant that helps security clearance adjudicators organize case file information. You do NOT make approve/deny recommendations. Your job is to:

1. Read the case file text provided.
2. Identify which of the following adjudicative guidelines are relevant to information in the case:
{GUIDELINES}

3. For each relevant guideline, extract the specific evidence from the case file that relates to it.
4. Note anything that is unclear, missing, or unverified.
5. Suggest one targeted follow-up question the adjudicator could ask to resolve each unclear item.

Format your response clearly with a section for each relevant guideline, like this:

## Guideline [Letter] - [Name]
**Evidence:** [what the case file says]
**Unclear/Missing:** [what's not documented or verified, if anything]
**Suggested Follow-up:** [a specific question, if applicable]

Only include guidelines that are actually relevant to the case file. Do not recommend approval or denial."""

@app.route("/analyze", methods=["POST"])
def analyze():
    case_text = request.form.get("case_text", "")

    if not case_text.strip():
        return jsonify({"error": "No case text provided"}), 400

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the case file:\n\n{case_text}"}
        ]
    )

    result = response.choices[0].message.content
    return jsonify({"result": result})

if __name__ == "__main__":
    app.run(debug=True, port=5000)