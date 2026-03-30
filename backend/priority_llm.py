import os
import re
from google import genai

_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=_api_key) if _api_key else None

def get_llm_priority(email_text, subject="", sender=""):
    prompt = f"""
Classify this email into ONE priority rank:

0: Mail from Chief Secretary
1: Court-related matters
2: Legal Issues
3: CMO-related matters
5: Fund release cases
6: Time-sensitive student issues

Return ONLY the number.

Email:
Sender: {sender}
Subject: {subject}
Content: {email_text}
"""

    try:
        if client is None:
            return 99

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        result = (getattr(response, "text", "") or "").strip()

        match = re.search(r"\d+", result)
        if match:
            return int(match.group())

        return 99
    except:
        return 99

def apply_thread_escalation(priority, followup_count):
    # If many follow-ups, increase priority
    if followup_count > 3 and priority in [5, 6]:
        return 2  # escalate to legal-level seriousness
    return priority