import os
import json
import re
import threading
import time
from collections import deque
from google import genai
from dotenv import load_dotenv
from ai_utils import generate_content_with_fallback, ULTIMATE_FALLBACK_LIST

load_dotenv()

_api_key = (
    os.getenv("PRIORITY_GOOGLE_API_KEY")
    or os.getenv("PRIORITY_GEMINI_API_KEY")
)
client = genai.Client(api_key=_api_key) if _api_key else None
_LLM_PRIORITY_MAX_CALLS = int(os.getenv("PRIORITY_LLM_MAX_CALLS", "1"))
_LLM_PRIORITY_WINDOW_SECONDS = int(os.getenv("PRIORITY_LLM_WINDOW_SECONDS", "60"))
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
    if client is None: return None
    if not _allow_llm_call():
        print("Priority LLM rate limit reached; using heuristic fallback.")
        return None
    try:
        response = generate_content_with_fallback(
            client=client,
            contents=prompt,
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Priority-LLM"
        )
        return getattr(response, "text", "") if response else None
    except Exception as exc:
        print(f"Priority LLM call failed: {exc}")
        return None

# --- EXPERT RUBRIC (0-6) ---
PRIORITY_RUBRIC = """
0: Chief Secretary / Cabinet / Highest Government Authority (Mandatory Command)
1: Court orders, RTI Matters, Examination Paper Leakage/Breach, Major Student Accidents (Critical)
2: Anti-Ragging Complaints, FIR cases, CMO Issues, Ministerial References (High Stakes)
3: Service Matters (Salary/Pension Delays), Suspensions / Disciplinary, Financial Fraud (Integrity)
4: Tenders / Procurement (Deadlines), Seat Matrix, Accreditation (NAAC/NBA)
5: Ordinary Leave Requests, Admissions, Semester / Examination routine, Scholarship Queries (Routine)
6: Miscellaneous, routine queries, website feedback, or general information (Standard)

Rules:
- Increase urgency by 1 (lower number) if immediate deadlines or repeat follow-ups (>3) are mentioned, capped at Level 2.
- Student safety and major integrity breaches (leaks) MUST be Level 1.
"""

def get_llm_priority(email_text, subject="", sender=""):
    prompt = f"""
You are an expert email triage assistant for a government education department.
Analyze this email and assign ONE priority rank from the rubric below:

RUBRIC:
{PRIORITY_RUBRIC}

Return ONLY a single digit (0-6). No explanation.

Email:
Sender: {sender}
Subject: {subject}
Content: {email_text}
"""
    result = _score_with_llm(prompt)
    if not result: return None
    match = re.search(r"\d+", result)
    return int(match.group()) if match else None

def get_batch_triage(emails):
    if not emails or client is None: return {}
    
    emails_block = ""
    for e in emails:
        emails_block += f"ID: {e['id']}\nSENDER: {e['sender']}\nSUBJECT: {e['subject']}\nCONTENT: {e['content'][:700]}...\n---\n"

    categories_list = [
        "Suspension / Disciplinary", "Legal Issues", "RTI Matters", "CMO Issues",
        "Semester / Examination", "Scholarship & Fee Concession", "Purchase / Procurement Issues",
        "Cash Issues", "Anti-Ragging Complaints", "Accreditation & Ranking", "Service Matters",
        "Appointment Issues", "Transfer Cases", "Inspection Matters", "Seat Matrix Issues", "Miscellaneous"
    ]

    prompt = f"""
You are an expert triage assistant for a government education department. 
Analyze the following batch of emails and assign BOTH a category and a priority rank (0-6) to each.

CATEGORIES:
{", ".join(categories_list)}

PRIORITY RUBRIC:
{PRIORITY_RUBRIC}

Rules:
- Return YOUR RESPONSE AS A VALID JSON OBJECT ONLY.
- Format: {{ "EMAIL_ID": {{ "priority": 0-6, "category": "One of the listed categories" }}, ... }}

EMAILS TO PROCESS:
{emails_block}
"""
    result_text = _score_with_llm(prompt)
    if not result_text: return {}

    try:
        cleaned_json = result_text.strip()
        if "{" in cleaned_json and "}" in cleaned_json:
            cleaned_json = cleaned_json[cleaned_json.find("{"):cleaned_json.rfind("}")+1]
        
        triage_data = json.loads(cleaned_json)
        cleaned_results = {}
        for k, v in triage_data.items():
            clean_k = str(k).strip().lower()
            if clean_k.startswith("id:"): clean_k = clean_k[3:].strip()
            
            cat = v.get("category", "Miscellaneous")
            if cat not in categories_list: cat = "Miscellaneous"
            
            cleaned_results[clean_k] = {
                "priority": int(v.get("priority", 6)),
                "category": cat
            }
        return cleaned_results
    except Exception as e:
        print(f"Batch LLM triage failed: {e}")
        return {}

def apply_thread_escalation(priority, followup_count):
    if (followup_count or 0) > 3 and (priority or 5) > 2:
        return 2  
    return priority