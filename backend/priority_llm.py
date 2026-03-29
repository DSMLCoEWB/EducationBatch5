import google.generativeai as genai
import os
import re

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")


def apply_thread_escalation(base_priority, followup_count):
    """Escalate priority for follow-up threads (lower rank number = higher priority)."""
    try:
        priority = int(base_priority)
    except Exception:
        priority = 99

    try:
        count = int(followup_count)
    except Exception:
        count = 0

    if count <= 0:
        return priority

    # Escalate by one level for follow-up threads, but do not go above 0.
    return max(0, priority - 1)

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
        response = model.generate_content(prompt)
        result = response.text.strip()

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