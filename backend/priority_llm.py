import os
import json
import re
import threading
import time
from collections import deque
from google import genai
from dotenv import load_dotenv

load_dotenv()

_api_key = (
    os.getenv("PRIORITY_GOOGLE_API_KEY")
    or os.getenv("PRIORITY_GEMINI_API_KEY")
)
# Note: PRIORITY_LLM will only operate if a dedicated key is provided to avoid saturating the main key.
client = genai.Client(api_key=_api_key) if _api_key else None
_LLM_PRIORITY_MAX_CALLS = int(os.getenv("PRIORITY_LLM_MAX_CALLS", "5"))
_LLM_PRIORITY_WINDOW_SECONDS = int(os.getenv("PRIORITY_LLM_WINDOW_SECONDS", "300"))
_llm_call_timestamps: deque[float] = deque()
_llm_call_lock = threading.Lock()


def _allow_llm_call() -> bool:
    now = time.monotonic()
    window_start = now - _LLM_PRIORITY_WINDOW_SECONDS

    with _llm_call_lock:
        while _llm_call_timestamps and _llm_call_timestamps[0] < window_start:
            _llm_call_timestamps.popleft()

        if len(_llm_call_timestamps) >= _LLM_PRIORITY_MAX_CALLS:
            return False

        _llm_call_timestamps.append(now)
        return True


def _score_with_llm(prompt: str) -> str | None:
    if client is None:
        return None

    if not _allow_llm_call():
        print("Priority LLM rate limit reached; using heuristic fallback.")
        return None

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception as exc:
        print(f"Priority LLM call failed: {exc}")
        return None

def get_llm_priority(email_text, subject="", sender=""):
    prompt = f"""
You are an expert email triage assistant for a government education department.

Analyze this email carefully considering:
- The SENDER's authority level
- The URGENCY and time-sensitivity of the issue
- The LEGAL or administrative implications
- The IMPACT on students or institutions

Then assign ONE priority rank from below:

0: Chief Secretary / highest authority communication (Critical)
1: Court orders, RTI, legal notices (Immediate Action - Critical)
2: Legal disputes, FIR cases, serious misconduct, suspension cases (High)
3: CMO office, ministerial, MLA-level, or higher education office matters (High)
4: Financial urgency: Fund release, salary disbursement, increment issues (Medium)
5: Urgent student issues: Exams, results, admission deadlines (Medium)
6: General grievances, routine queries, portal issues, or feedback (Low Priority)

Rules:
- If the email expresses frustration, repeated follow-ups, or mentions deadlines, increase urgency by 1 level (lower number).
- If the sender holds a high official position, prioritize accordingly.
- Return ONLY a single digit (0-6). No explanation.

Email:
Sender: {sender}
Subject: {subject}
Content: {email_text}
"""

    result = _score_with_llm(prompt)
    if not result:
        return None

    match = re.search(r"\d+", result)
    if match:
        return int(match.group())

    return None

def get_batch_priorities(emails):
    """
    Emails: list of {id, subject, sender, content}
    Returns: dict of {id: priority}
    """
    if not emails or client is None:
        return {}

    # Format emails into a single block
    emails_block = ""
    for e in emails:
        emails_block += f"ID: {e['id']}\nSENDER: {e['sender']}\nSUBJECT: {e['subject']}\nCONTENT: {e['content'][:500]}...\n---\n"

    prompt = f"""
You are an expert triage assistant for a government education department. 
Analyze the following batch of emails and assign a priority rank (0-6) to each.

PRIORITY LEVELS (0-6):
0: Chief Secretary / highest authority (Critical)
1: Court orders, RTI, legal notices (Immediate Action - Critical)
2: Legal disputes, FIR cases, misconduct, suspension (High)
3: CMO office, ministerial, MLA, higher education office (High)
4: Financial urgency: Salary, fund release, increments (Medium)
5: Urgent student issues: Exams, results, admission deadlines (Medium)
6: General grievances, routine queries, feedback (Low Priority)

Rules:
- If follow-up mentions or deadlines exist, increase urgency (lower number).
- Return YOUR RESPONSE AS A VALID JSON OBJECT ONLY.
- Format: {{ "EMAIL_ID": PRIORITY_NUMBER, ... }}

EMAILS TO PROCESS:
{emails_block}
"""

    result_text = _score_with_llm(prompt)
    if not result_text:
        return {}

    try:
        print(f"DEBUG RAW AI RESPONSE: {result_text}")
        cleaned_json = result_text.strip()
        if cleaned_json.startswith("```"):
            # Remove start/end backticks and any "json" tag
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_json, re.DOTALL)
            if match:
                cleaned_json = match.group(1)

        # Aggressive cleaning: remove anything that is not part of the JSON object
        # In case the LLM adds text before/after the backticks
        if "{" in cleaned_json and "}" in cleaned_json:
            cleaned_json = cleaned_json[cleaned_json.find("{"):cleaned_json.rfind("}")+1]

        priorities = json.loads(cleaned_json)

        # Final ID normalization for matching
        cleaned_priorities = {}
        for k, v in priorities.items():
            clean_k = str(k).strip().lower()
            # If the AI adds "ID: " or quotes, strip them
            if clean_k.startswith("id:"):
                clean_k = clean_k[3:].strip()
            cleaned_priorities[clean_k] = int(v)

        return cleaned_priorities
    except Exception as e:
        print("Batch LLM scoring failed: " + str(e))
        print(f"RAW TEXT was: {result_text[:200]}...") # Log start of raw text for debugging
        return {}

def apply_thread_escalation(priority, followup_count):
    # If many follow-ups, increase priority
    if followup_count > 3 and priority in [4, 5]:
        return 2  # escalate to legal-level seriousness
    return priority