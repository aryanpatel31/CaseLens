# CaseLens

AI-assisted case review for security clearance adjudication. Organizes evidence across multiple source documents, flags contradictions, cites every claim back to its source, and checks its own work before a human ever sees the output. It does not make approve or deny recommendations.

## The Problem

Security clearance investigations have sped up in recent years. Adjudication has not.

- Top Secret: ~243 days total, 126 of which are adjudication alone (DCSA, Q3 FY2026)
- Secret: ~197 days total, 117 of which are adjudication (DCSA, Q3 FY2026)
- ~3.7 million Americans hold an active clearance
- ~300,000 cases move through this pipeline each year

The bottleneck isn't the judgment call at the end. It's finding, organizing, and verifying scattered information fast enough to get there.

## What It Does

1. Reviewer uploads a case file (can be multiple documents: SF-86, investigator report, financial records, employment verification, travel records, etc.)
2. Personal information is redacted before anything reaches an AI model
3. An Analyst agent maps the case against the 13 federal adjudicative guidelines, with citations
4. A Reconciler agent cross-references the documents for contradictions
5. A Verifier agent audits the Analyst's output, checking citation accuracy, rating consistency, and guideline misclassification
6. Reviewer sees a color-coded dashboard, can click any citation to jump to the source line, and can ask follow-up questions about the case

## Architecture

```
Upload → Redact PII → Analyst Agent → Reconciler Agent → Verifier Agent → Dashboard
                                              ↓
                                     (runs if 2+ files)
```

Three agents, each with a narrow job, each one's output feeding into the next. Splitting the work this way keeps each step more reliable and makes the system able to catch its own errors. During testing, the Analyst filed the same IT policy violation under two different guidelines, and the Verifier caught it.

## Features

- Multi-file drag-and-drop upload
- PII redaction (names) before any model call
- 13-guideline dashboard with green/yellow/red risk ratings
- Cross-source contradiction detection
- Self-auditing verifier agent
- Clickable, line-level citations with scroll-and-highlight
- Interactive Q&A grounded strictly in the uploaded case files

## Tech Stack

- Backend: Python, Flask
- Frontend: HTML, CSS, JavaScript
- LLM: Groq API, `openai/gpt-oss-120b`
- NLP: spaCy (`en_core_web_sm`) for PII redaction

## Project Structure

```
app.py                 Flask routes and agent pipeline
prompts.py             System prompts for Analyst, Reconciler, Verifier, Chat
templates/index.html   Page structure
static/style.css       Styling
static/script.js       Dashboard rendering, citation highlighting, chat
data/                  Synthetic test case files
```

## Setup

```bash
conda create -n caselens python=3.11 -y
conda activate caselens
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Run it:

```bash
python app.py
```

App runs on `http://127.0.0.1:5001` (port 5001 used instead of 5000 to avoid conflicts with AirPlay Receiver on macOS).
