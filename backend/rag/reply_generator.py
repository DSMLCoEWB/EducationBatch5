import os
import json
import hashlib
from typing import Dict, Any, List
from dotenv import load_dotenv

from rag.retriever import retrieve_policy_chunks

from google import genai

# ---------- CONFIG ----------
load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if not API_KEY or "your_google_api_key" in API_KEY or "your_gemini_api_key" in API_KEY:
    print(f"❌ ERROR: Gemini API key is missing. KEY_LEN: {len(API_KEY) if API_KEY else 0}")

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"❌ Gemini Client Init Failed: {e}")

# ---------- SYSTEM PROMPT ----------
SYSTEM_PROMPT = """
You are a professional grievance redressal assistant.

Rules:
- Use ONLY the provided policy clauses
- Do NOT invent rules
- If policy is unclear, say "Policy does not specify further details"
- Keep response formal and complete
"""

FALLBACK_TEMPLATE = """
Subject: RE: {subject}

Dear Sir/Madam,

Your grievance has been received and is under review. 
The institution will process the matter as per applicable policy provisions.

Sincerely,
Grievance Support Desk
""".strip()


def build_prompt(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]]) -> str:
    context = "\n\n".join(
        f"[Clause {c['metadata']['clause_id']}] {c['text']}"
        for c in chunks
    )

    return f"""
USER EMAIL:
Subject: {subject}
From: {sender}

{email}

POLICY CONTEXT:
{context}

TASK:
Write a complete professional reply email using ONLY the policy context.

Format:
Subject: RE: {subject}
Dear Sir/Madam,

<clear explanation based on policy>

Sincerely,
Grievance Support Desk
""".strip()


def generate_reply(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]]) -> str:
    if not client:
        return ""

    prompt = build_prompt(subject, sender, email, chunks)

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", # Updated to a valid model name if gemini-2.5-flash was a typo or preview
            contents=prompt,
            config={
                "temperature": 0.1,
                "max_output_tokens": 500
            }
        )
        reply = (response.text or "").strip()
        return reply
    except Exception as e:
        print(f"❌ LLM Generation Error: {e}")
        return ""


def generate_suggested_reply_with_evidence(
    email_content: str,
    email_subject: str = "Query",
    sender: str = "Sir/Madam",
    category: str = ""
) -> Dict[str, Any]:
    """
    Main entry point for suggested reply generation.
    Ensures safe JSON output for frontend.
    """
    
    # Handle "nan" sender bug (Task 6)
    if not sender or str(sender).lower() == "nan":
        sender = "Sir/Madam"
    
    if not email_subject or str(email_subject).lower() == "nan":
        email_subject = "Your Inquiry"

    query = f"{email_subject} {email_content}".strip()
    
    # Task 3 requirement: retrieve chunks
    retrieved = []
    try:
        retrieved = retrieve_policy_chunks(query)
    except Exception as e:
        print(f"❌ Retrieval failed: {e}")
        retrieved = []

    # Generate reply with safety (Task 4)
    reply = ""
    status = "ok"
    
    if retrieved:
        reply = generate_reply(email_subject, sender, email_content, retrieved)
    
    # Fallback logic: if empty or too short (Task 4)
    if not reply or len(reply) < 50:
        reply = FALLBACK_TEMPLATE.format(subject=email_subject)
        status = "fallback" if retrieved else "no_match"

    # Format evidence safely
    evidence = [
        {
            "clause_id": c["metadata"].get("clause_id", "N/A"),
            "section": c["metadata"].get("section", "General"),
            "score": round(c.get("score", 0.0), 3),
            "text": c.get("text", "")[:300]
        }
        for c in retrieved
    ]

    # Task 5: NEVER break frontend
    return {
        "suggested_reply": reply,
        "evidence": evidence,
        "status": status
    }


def generate_suggested_reply(email_content: str, email_subject: str = "", sender: str = "") -> str:
    result = generate_suggested_reply_with_evidence(email_content, email_subject, sender)
    return result.get("suggested_reply", "Error generating reply")
