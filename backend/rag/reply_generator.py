import os
import json
import hashlib
from typing import Dict, Any, List
from dotenv import load_dotenv

from rag.retriever import retrieve_policy_chunks
from google import genai
from ai_utils import generate_content_with_fallback, ULTIMATE_FALLBACK_LIST

# ---------- CONFIG ----------
load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if not API_KEY or "your_google_api_key" in API_KEY or "your_gemini_api_key" in API_KEY:
    print(f"[ERROR]: Gemini API key is missing. KEY_LEN: {len(API_KEY) if API_KEY else 0}")

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"[ERROR]: Gemini Client Init Failed: {e}")

# ---------- SYSTEM PROMPT ----------
SYSTEM_PROMPT = """
You are a senior professional grievance redressal officer for an educational institution.

Primary Goal: Generate a formal, helpful, and policy-grounded email reply.

Rules:
1. Strict Grounding: Use ONLY the provided policy context.
2. Complete Response: Output a FULL email body (Salutation, Body, Signature).
3. NO REDUNDANT SUBJECT: DO NOT include a "Subject:" line in your response. The system handles the subject separately.
4. NO HARD WRAPPING: Do NOT insert line breaks within paragraphs. Let the text flow naturally. Only use double newlines between paragraphs.
5. Minimum Length: The body must be 3-5 sentences minimum.
6. Policy Citation: You MUST explicitly mention specific clause IDs (e.g., "As per MSC-06...") to support your statements.
7. Delay Handling: If the user query is about a delay or pending status, you MUST mention the specific escalation path (e.g., nodal officer) or response timelines from the policy.
8. Tone: Professional, authoritative yet respectful.
9. Language: Formal English.

If the provided policy context is insufficient, weak, or unrelated:
- DO NOT attempt to infer or combine unrelated clauses
- Respond stating that no relevant policy clause is available
- Do not fabricate policy references
"""

FALLBACK_TEMPLATE = """
Dear Sir/Madam,

Your grievance has been received and is under review. 
The institution will process the matter as per applicable policy provisions.

Sincerely,
Grievance Support Desk
""".strip()


def build_prompt(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]], attachment_text: str = "") -> str:
    context = "\n\n".join(
        f"[Clause {c['metadata']['clause_id']}] {c['text']}"
        for c in chunks
    )

    return f"""
{SYSTEM_PROMPT}

USER EMAIL:
Subject: {subject}
From: {sender}
Content: {email}

ATTACHMENT CONTENT (OCR):
{attachment_text if attachment_text else "None"}

POLICY CONTEXT:
{context}

TASK:
Write a professional reply email to the student/staff member. 
- You MUST use the policy context provided.
- You MUST mention specific clause IDs (e.g., MSC-03, SUS-01).
- If there's a delay mentioned (e.g., 30 days pending), refer back to the specific delay/escalation rules in the policy chunks.
- Ensure the email starts with "Dear {sender}," and ends with "Sincerely, Grievance Support Desk".
- IMPORTANT: DO NOT include a "Subject:" line. Start directly with the Salutation.
- IMPORTANT: Do NOT hard-wrap the text.

OUTPUT FORMAT:
Dear {sender},

[Professional body using policy context and referencing clause IDs]

Sincerely,
Grievance Support Desk
""".strip()


def generate_reply(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]], attachment_text: str = "") -> str:
    if not client:
        return ""

    prompt = build_prompt(subject, sender, email, chunks, attachment_text)

    response = generate_content_with_fallback(
        client=client,
        contents=prompt,
        model_list=ULTIMATE_FALLBACK_LIST,
        label="RAG-Generator"
    )
    if not response:
        return ""

    reply = ""
    if response and response.text:
        reply = response.text.strip()
        
    # Task 2: Safety & Length checks
    if not reply or len(reply) < 30:
        print(f"[WARN]: LLM response too short ({len(reply) if reply else 0} chars)")
        return ""
        
    # Task: Strip redundant "Subject:" if LLM prepended it
    if "subject:" in reply.lower():
        lines = reply.split('\n')
        lines = [l for l in lines if not l.strip().lower().startswith("subject:")]
        reply = "\n".join(lines).strip()

    return reply


def generate_suggested_reply_with_evidence(
    email_content: str,
    email_subject: str = "",
    sender: str = "",
    category: str = "",
    attachment_content: str = ""
) -> Dict[str, Any]:
    """
    Main entry point for suggested reply generation.
    Ensures safe JSON output and provides mandatory debug logs.
    """
    
    # Task 5 & 6: Fix Sender + Subject + "nan" bug
    clean_sender = str(sender) if sender and str(sender).lower() != "nan" else "Sir/Madam"
    clean_subject = str(email_subject) if email_subject and str(email_subject).lower() != "nan" else "Your Inquiry"

    # Best-in-class RAG: Add category and attachment context to the search query for higher parity
    query = f"Category: {category} | {clean_subject} {email_content} {attachment_content}".strip()
    
    # Retrieval
    retrieved = []
    try:
        retrieved = retrieve_policy_chunks(query)
    except Exception as e:
        print(f"[ERROR]: Retrieval failed: {e}")
        retrieved = []

    # Task 3: SAFE FALLBACK for empty Context
    if not retrieved:
        status = "no_policy"
        print("[WARN]: No relevant policy chunks found. Applying safe fallback.")
        reply = f"""Subject: RE: {clean_subject}
Dear {clean_sender},
We regret to inform you that no specific institutional policy clause directly addresses your query.
Your concern has been forwarded to the concerned authority for review.
Sincerely,
Grievance Support Desk"""
        
        evidence = []
    else:
        # Generation
        reply = ""
        status = "ok"
        reply = generate_reply(clean_subject, clean_sender, email_content, retrieved, attachment_content)
        
        # Smarter Fallback: lenient, case-insensitive check
        # Accept any common professional closing — don't throw away valid replies
        VALID_CLOSINGS = ("sincerely", "regards", "yours faithfully", "best regards", "with regards", "yours truly")
        reply_lower = reply.lower() if reply else ""
        has_greeting = "dear" in reply_lower
        has_closing = any(c in reply_lower for c in VALID_CLOSINGS)
    
        if not reply or len(reply) < 80 or not has_greeting or not has_closing:
            print(f"[WARN]: Fallback triggered -> has_greeting={has_greeting}, has_closing={has_closing}, reply_len={len(reply) if reply else 0}")
            reply = FALLBACK_TEMPLATE.format(subject=clean_subject)
            status = "fallback"

        # Formatting evidence
        evidence = [
            {
                "clause_id": c["metadata"].get("clause_id", "N/A"),
                "section": c["metadata"].get("section", "General"),
                "score": round(c.get("score", 0.0), 3),
                "text": str(c.get("text", "")).strip()
            }
            for c in retrieved
        ]

    # Task 8: MANDATORY Debug Logs
    top_score = evidence[0]["score"] if evidence else 0.0
    clause_ids = [e["clause_id"] for e in evidence]
    resp_len = len(reply)
    
    print("-" * 50)
    print(f"[DEBUG] Top retrieval score: {top_score}")
    print(f"[DEBUG] Retrieved clause IDs: {clause_ids}")
    print(f"[DEBUG] LLM response length: {resp_len}")
    print(f"[DEBUG] Final status: {status}")
    print("-" * 50)

    # Best-in-class metadata
    trust_score = top_score if status == "ok" else (0.4 if status == "fallback" else 0.0)
    trust_label = "High" if trust_score > 0.7 else ("Medium" if trust_score > 0.55 else "Low")
    
    # Task 7: NEVER break frontend
    return {
        "suggested_reply": reply,
        "evidence": evidence,
        "status": status,
        "trust_score": trust_score,
        "trust_label": trust_label,
        "generation_mode": "RAG-Multimodal-v2",
        "grounding_report": {
            "clauses_used": clause_ids,
            "attachment_processed": bool(attachment_content),
            "retrieval_success": len(evidence) > 0
        }
    }


def generate_suggested_reply(email_content: str, email_subject: str = "", sender: str = "") -> str:
    result = generate_suggested_reply_with_evidence(email_content, email_subject, sender)
    return result.get("suggested_reply", "Error generating reply")
