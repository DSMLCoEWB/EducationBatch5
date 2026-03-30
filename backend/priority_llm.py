import os
import re
from google import genai

_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=_api_key) if _api_key else None

def get_llm_priority(email_text, subject="", sender=""):
    prompt = f"""
You are an expert email triage assistant for a government education department.

Analyze this email carefully considering:
- The SENDER's authority level
- The URGENCY and time-sensitivity of the issue
- The LEGAL or administrative implications
- The IMPACT on students or institutions

Then assign ONE priority rank from below:

0: Chief Secretary / highest authority communication
1: Court orders, RTI, legal notices requiring immediate action
2: Legal disputes, FIR cases, serious misconduct
3: CMO office, ministerial, or MLA-level matters
4: Fund release, salary disbursement, financial urgency and Urgent student issues (exam, result, admission deadlines)
5: General grievances, routine queries, informational

Rules:
- If the email expresses frustration, repeated follow-ups, or mentions deadlines, increase urgency by 1 level (lower number).
- If the sender holds a high official position, prioritize accordingly.
- Return ONLY a single digit (0-5). No explanation.

Email:
Sender: {sender}
Subject: {subject}
Content: {email_text}
"""

    try:
        if client is None:
            return 5
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        result = (getattr(response, "text", "") or "").strip()

        match = re.search(r"\d+", result)
        if match:
            return int(match.group())

        return 5
    except:
        return 5

def apply_thread_escalation(priority, followup_count):
    # If many follow-ups, increase priority
    if followup_count > 3 and priority in [4, 5]:
        return 2  # escalate to legal-level seriousness
    return priority