import os
import json
import re
import threading
import time
from collections import deque
from google import genai
from dotenv import load_dotenv
from services.ai_utils import generate_content_with_fallback, ULTIMATE_FALLBACK_LIST
from core.logging import get_logger

load_dotenv()
logger = get_logger("triage_llm")

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
    # Bypass rate limits for local models to ensure smooth demo ingest
    from config import AI_PREFER_LOCAL
    if AI_PREFER_LOCAL:
        return True
        
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
        logger.warning("Triage LLM rate limit reached; using heuristic fallback.")
        return None
    try:
        response = generate_content_with_fallback(
            client=client,
            contents=prompt,
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Triage-LLM"
        )
        if response:
            try:
                return response.text
            except:
                return str(response)
        return None
    except Exception as exc:
        logger.error(f"Triage LLM call failed: {exc}")
        return None

# --- EXPERT RUBRIC (0-3) ---
PRIORITY_RUBRIC = """
PRIORITY LEVEL DEFINITIONS & TOPIC-BASED MAPPINGS:

- Priority 0: CRITICAL / IMMEDIATE ACTION REQUIRED
  * Subject Matter & Topics:
    - RTI matters (all types — applications, appeals, reports, queries).
    - Active court orders, show-cause notices, or judicial directives.
    - Commands or review meeting mandates from highest government authorities (Chief Secretary, Cabinet, Minister's Office).
    - Leakage of examination papers or major institutional security breaches.
    - Major student accidents, medical emergencies, or safety incidents on campus.

- Priority 1: HIGH URGENCY / HIGH STAKES
  * Subject Matter & Topics:
    - CMO portal grievances or Ministerial references.
    - Anti-Ragging matters and student safety issues.
    - Salary, pension, gratuity, arrear, pay fixation, or seniority disputes.
    - Official suspension notices or disciplinary proceedings (chargesheet, misconduct).
    - Active financial fraud or corruption allegations.
    - Contextual Triggers: Extreme sender distress, anger, frustration, or threats of academic/financial debarment (e.g., student plea to continue education after fee issues/debarment).

- Priority 2: ROUTINE ADMINISTRATIVE / MEDIUM STAKES
  * Subject Matter & Topics:
    - Academic career advancement (e.g., Career Advancement Scheme / CAS promotions).
    - Scholarship & fee concession queries — SVMCM, Freeships, Student Credit Cards, Oasis (routine portal issues or applications).
    - Tenders, procurement, GeM portal payment claims, or fund sanctions (routine — active fraud is Priority 1).
    - Accreditation and ranking affairs (e.g., NAAC, NIRF, NBA conclaves, meetings, preparation).
    - Transfer orders, posting, deputation, or appointment letters (all types; contested cases may be escalated by the LLM contextually).
    - Audit and inspection schedules (e.g., CAG audit reports, physical inspections of colleges).
    - Seat matrix submissions, entry updates, or routine seat allocation reports.
    - Routine compliance filings or administrative reporting (e.g., anti-ragging committee status reports — not active incidents).

- Priority 3: LOW URGENCY / ROUTINE NOTIFICATIONS & MISCELLANEOUS
  * Subject Matter & Topics:
    - Invitations to meetings, seminars, workshops, or student induction programs.
    - Advertisements, training programs, or workshop announcements.
    - General website feedback, non-urgent suggestions, or routine public inquiries.
    - General newsletters, circulars, or generic informational forwards.

Rules:
- Increase urgency (lower number), capped at Level 1, if ANY of the following are detected:
  (a) User frustration, anger, or emotionally distressed tone or a truly urgent or time-sensitive matter.
  (b) Excessive unanswered follow-ups (>3 follow-ups without resolution) or evidence of a significantly delayed departmental response.
- Level 0 is reserved for Chief Secretary commands, court orders, major student accidents, institutional breaches, and RTI matters.
- DO NOT classify general student "inquiries" or "enquiries" as Suspension/Disciplinary unless there is explicit mention of misconduct or penalties.
- "SVMCMS", "Oasis", and "K3" are strictly Scholarship & Fee Concession matters.
"""


def get_batch_triage(emails, user_email: str = None):
    """Sends a batch of emails to the LLM for high-precision triage using numeric mapping."""
    if not emails or client is None: return {}
    
    # 1. Create a stable numeric map to avoid sending complex Gmail IDs to LLM
    id_map = {}
    emails_block = ""
    for idx, e in enumerate(emails, 1):
        actual_id = str(e.get('id', ''))
        id_map[str(idx)] = actual_id
        
        # Build the text block for AI to read
        full_content = e.get('content', '') or ""
        att_full = e.get('attachment_content', '') or ""
        
        f_count = e.get('followup_count', 0)
        emails_block += f"INDEX: {idx}\nSENDER: {e.get('sender')}\nSUBJECT: {e.get('subject')}\nFOLLOW-UP COUNT: {f_count}\nCONTENT: {full_content}\n"
        if att_full:
            emails_block += f"ATTACHMENT_TEXT: {att_full}\n"
        emails_block += "---\n"

    from db.repository import get_active_categories
    active_cats = get_active_categories(user_email) if user_email else []
    if not active_cats:
        categories_list = ["Miscellaneous"]
    else:
        categories_list = [cat['name'] for cat in active_cats]

    # Load dynamic priority rubric based on layman-configured rules
    dynamic_priority_rubric = ""
    global_rules = ""
    if user_email:
        try:
            from db.repository import get_priority_rules, get_global_rules
            rules = get_priority_rules(user_email)
            global_rules = get_global_rules(user_email)
            rubric_parts = []
            for r in sorted(rules, key=lambda x: x["priority"]):
                keywords_str = ", ".join(r["keywords"])
                desc = r.get("description", "").strip()
                part = f"- Level {r['priority']} ({r['label']}):"
                if desc:
                    part += f"\n  Criteria/Instructions: {desc}"
                if keywords_str:
                    part += f"\n  Trigger Keywords (Boosters): {keywords_str}"
                rubric_parts.append(part)
            dynamic_priority_rubric = "\n".join(rubric_parts)
        except Exception as e:
            logger.error(f"⚠️ [LLM Triage] Dynamic priority rubric load failed: {e}")

    if not dynamic_priority_rubric:
        dynamic_priority_rubric = PRIORITY_RUBRIC
    if not global_rules:
        try:
            from db.repository import get_global_rules
            global_rules = get_global_rules(user_email)
        except Exception:
            global_rules = ""

    from db.repository import get_system_role
    custom_role = get_system_role(user_email) if user_email else "the Department of Education"

    prompt = f"""
You are an expert triage assistant acting on behalf of the {custom_role}. 
Analyze the following batch of emails and assign BOTH a category and a priority rank (0-3) to each.

CATEGORIES:
{", ".join(categories_list)}

PRIORITY RUBRIC:
{dynamic_priority_rubric}

Global Rules & Triage Guardrails:
{global_rules}

Rules:
- Return YOUR RESPONSE AS A VALID JSON OBJECT ONLY.
- Format: {{ "INDEX": {{ "priority": 0-3, "category": "One of the listed categories" }}, ... }}
- Use the numeric INDEX provided for each email.

EMAILS TO PROCESS:
{emails_block}
"""
    result_text = _score_with_llm(prompt)
    if not result_text: 
        print("  [!] LLM returned no text for this batch.")
        return {}

    try:
        cleaned_json = result_text.strip()
        if "{" in cleaned_json and "}" in cleaned_json:
            cleaned_json = cleaned_json[cleaned_json.find("{"):cleaned_json.rfind("}")+1]
        
        triage_data = json.loads(cleaned_json)
        final_results = {}
        
        for idx_key, v in triage_data.items():
            # Map numeric index back to real DB ID
            actual_id = id_map.get(str(idx_key))
            if not actual_id:
                continue
            
            # Case-insensitive matching for robustness
            cat = v.get("category", "Miscellaneous")
            matched_cat = next((c for c in categories_list if c.lower() == cat.lower()), "Miscellaneous")
            
            final_results[actual_id] = {
                "priority": int(v.get("priority", 3)),
                "category": matched_cat
            }
        return final_results
    except Exception as e:
        logger.error(f"❌ [Triage] Failed to parse AI batch results: {e}. Raw: {result_text[:200]}")
        return {}
