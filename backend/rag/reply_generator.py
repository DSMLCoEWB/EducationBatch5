import os
import json
import hashlib
from typing import Dict, Any, List
from dotenv import load_dotenv

from rag.retriever import retrieve_policy_chunks
import openai
from ai_utils import generate_content_with_fallback

# ---------- CONFIG ----------
load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

if not API_KEY or "your_google_api_key" in API_KEY or "your_gemini_api_key" in API_KEY:
    print(f"[ERROR]: Gemini API key is missing. KEY_LEN: {len(API_KEY) if API_KEY else 0}")

client = None
if os.getenv("USE_LOCAL_LLM") == "true":
    client = openai.OpenAI(base_url=os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1"), api_key="ollama")
elif API_KEY:
    try:
        client = None # Gemini fallback removed
    except Exception as e:
        print(f"[ERROR]: Fallback init failed: {e}")

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


def build_prompt(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]], attachment_text: str = "", history_text: str = "", citizen_name: str = "Sir/Madam", is_current_sent: bool = False, has_unreplied: bool = False) -> str:
    context = "\n\n".join(
        f"[Clause {c['metadata']['clause_id']}] {c['text']}"
        for c in chunks
    )

    history_section = ""
    if history_text:
        history_section = f"""
CONVERSATION HISTORY (Previous turns):
{history_text}
---
"""
    
    # Identify if we are replying to a citizen inquiry or following up on our own outreach/reply
    is_follow_up = is_current_sent
    is_follow_up_hint = ""
    target_name = citizen_name if is_follow_up else sender
    
    if is_follow_up:
        if has_unreplied:
            # Citizen has reached out again since our last reply
            is_follow_up_hint = f"\n[NOTE: You are responding to a NEW FOLLOW-UP inquiry from {citizen_name}. Address their new points while maintaining consistency with the previous exchange.]\n"
        else:
            # We are sending another message even though the citizen hasn't replied yet
            is_follow_up_hint = f"\n[NOTE: You are drafting a PROACTIVE follow-up or correction to {citizen_name}. The student has NOT replied since your last email. Do NOT thank them for a follow-up inquiry; instead, provide updates or check for satisfaction regarding the previous exchange.]\n"

    return f"""
{SYSTEM_PROMPT}

{history_section}
{is_follow_up_hint}
CURRENT CONTEXT (The message you are responding to or following up on):
Subject: {subject}
From: {sender}
Content: {email}

CURRENT ATTACHMENT CONTENT (OCR):
{attachment_text if attachment_text else "None"}

POLICY CONTEXT (Use these clauses for evidence):
{context}

TASK:
Write a professional reply email to {target_name}. 
- You MUST address the current inquiry while remaining consistent with the previous conversation history.
- You MUST use the policy context provided.
- You MUST mention specific clause IDs (e.g., MSC-03, SUS-01).
- If there's a delay mentioned (e.g., 30 days pending), refer back to the specific delay/escalation rules in the policy chunks.
- Ensure the email starts with "Dear {target_name}," and ends with "Sincerely, Grievance Support Desk".
- IMPORTANT: DO NOT include a "Subject:" line. Start directly with the Salutation.
- IMPORTANT: Do NOT hard-wrap the text.

OUTPUT FORMAT:
Dear {target_name},

[Professional body using policy context and referencing clause IDs]

Sincerely,
Grievance Support Desk
""".strip()


def generate_reply(subject: str, sender: str, email: str, chunks: List[Dict[str, Any]], attachment_text: str = "", history_text: str = "", citizen_name: str = "Sir/Madam", is_current_sent: bool = False, has_unreplied: bool = False) -> str:
    if not client:
        return ""

    prompt = build_prompt(subject, sender, email, chunks, attachment_text, history_text, citizen_name, is_current_sent, has_unreplied)

    response = generate_content_with_fallback(
        client=client,
        contents=prompt,
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
    attachment_content: str = "",
    history: List[Dict[str, Any]] = [],
    email_id: str = None
) -> Dict[str, Any]:
    """
    Main entry point for suggested reply generation.
    Implemented 'Surgical RAG' with anchor-turn context windowing.
    """
    
    # 1. Prepare Surgical Context
    safe_history = history if history else []
    
    # Temporal Truncation: If targeting a specific message, ignore future context
    if email_id and safe_history:
        found_idx = -1
        for i, m in enumerate(safe_history):
            if str(m.get('id', '')) == str(email_id):
                found_idx = i
                break
        if found_idx != -1:
            safe_history = safe_history[:found_idx + 1]
            
    # History is sorted ASC (oldest first).
    # Step A: Find the unreplied block (all messages after the last "is_sent")
    unreplied_msgs = []
    anchor_turn = []
    
    rev_history = list(reversed(safe_history))
    last_sent_idx = -1
    for i, msg in enumerate(rev_history):
        content_upper = str(msg.get('content', '')).upper()
        subject_upper = str(msg.get('subject', '')).upper()
        is_seed = "AICOE-SEED" in content_upper or "AICOE-SEED" in subject_upper
        
        # A message is a 'Department Reply' ONLY if it was marked as sent 
        # AND it is NOT an internal seed/test grievance.
        if (msg.get('is_sent') or msg.get('isSent')) and not is_seed:
            last_sent_idx = i
            break
            
    if last_sent_idx == -1:
        # No department reply yet: everything is unreplied
        unreplied_msgs = rev_history[:3] # Cap at latest 3
    else:
        # Unreplied are those BEFORE the last_sent (in reversed list)
        unreplied_msgs = rev_history[:last_sent_idx][:3]
        # Anchor is the last reply...
        anchor_turn.append(rev_history[last_sent_idx])
        # ...and its ACTUAL citizen trigger (skip sequential dept replies)
        for j in range(last_sent_idx + 1, len(rev_history)):
            msg_j = rev_history[j]
            if not (msg_j.get('is_sent') or msg_j.get('isSent')):
                anchor_turn.append(msg_j)
                break
            
    # Step B: Retrieval Query Construction (Focus on Unreplied + current)
    # Include current email + its attachment content
    retrieval_query_parts = [f"Subject: {email_subject}", email_content, attachment_content]
    
    # If this is a follow-up (unreplied is empty and we have an anchor turn),
    # we should include the Trigger (the citizen's inquiry) in the search query.
    if not unreplied_msgs and len(anchor_turn) >= 2:
        trigger = anchor_turn[1] # [sent, trigger]
        retrieval_query_parts.append(trigger.get('content', ''))
        att_text_t = trigger.get('attachment_content') or trigger.get('attachmentContent', '')
        retrieval_query_parts.append(att_text_t)

    for m in unreplied_msgs:
        # Don't duplicate the current one if it was passed in history
        if m.get('id') != history[-1].get('id') if history else False:
            retrieval_query_parts.append(m.get('content', ''))
            att_text = m.get('attachment_content') or m.get('attachmentContent', '')
            retrieval_query_parts.append(att_text)
            
    # Step C: Generation Context (Surgical 3+2)
    # Combine the Anchor Turn (Previous Interaction) + Unreplied Block (Current Problem)
    # We want these in chronological order (oldest to newest) for the LLM.
    history_to_format = []
    
    # Add the Anchor Turn (oldest part of the context)
    if anchor_turn:
        # anchor_turn was [sent, trigger] in reversed order, so reverse it back
        history_to_format.extend(reversed(anchor_turn))
        
    # Add the Unreplied Block
    if unreplied_msgs:
        # unreplied_msgs was [newest, ..., oldest] in reversed order, so reverse it back
        history_to_format.extend(reversed(unreplied_msgs))
        
    history_lines = []
    for m in history_to_format:
        is_dept = bool(m.get('is_sent') or m.get('isSent'))
        role = "Dpt-Response (You)" if is_dept else "Citizen-Inquiry"
        date = m.get('date', '') or m.get('emailDate', '')
        # Only include messages that are not the current one (which is the main prompt)
        if m.get('id') != safe_history[-1].get('id') if safe_history else False:
            history_lines.append(f"[{role} @ {date}]: {m.get('content', '')[:500]}")
    
    history_text = "\n".join(history_lines)
    
    # Task 5 & 6: Fix Sender + Subject + "nan" bug
    clean_sender = str(sender) if sender and str(sender).lower() != "nan" else "Sir/Madam"
    clean_subject = str(email_subject) if email_subject and str(email_subject).lower() != "nan" else "Your Inquiry"

    # Best-in-class RAG: Add category and surgical context to search query
    retrieval_base = " ".join([p for p in retrieval_query_parts if p]).strip()
    query = f"Category: {category} | {retrieval_base}".strip()[:1000] # Cap search query length
    
    # Retrieval
    retrieved = []
    try:
        retrieved = retrieve_policy_chunks(query)
    except Exception as e:
        print(f"[ERROR]: Retrieval failed: {e}")
        retrieved = []

    # Find the most recent citizen in context to use as citizen_name
    # DEFAULT to Sir/Madam instead of clean_sender to avoid "Dear Dept" bugs
    citizen_name = "Sir/Madam"
    for m in history_to_format:
        if not (m.get('is_sent') or m.get('isSent')):
            val = str(m.get('sender', '')).split('<')[0].strip()
            if val and val.lower() != "nan":
                citizen_name = val
            # Keep searching to get the LATEST citizen in the context
            
    # Determine if the email being replied to was a sent message
    is_current_sent = bool(history[-1].get('is_sent') or history[-1].get('isSent')) if history else False
    has_unreplied = len(unreplied_msgs) > 0
    
    if not retrieved:
        status = "no_policy"
        print("[WARN]: No relevant policy chunks found. Applying safe fallback.")
        reply = f"""Subject: RE: {clean_subject}
Dear {citizen_name},
We regret to inform you that no specific institutional policy clause directly addresses your query.
Your concern has been forwarded to the concerned authority for review.
Sincerely,
Grievance Support Desk"""
        
        evidence = []
    else:
        # Generation
        reply = ""
        status = "ok"
        reply = generate_reply(clean_subject, clean_sender, email_content, retrieved, attachment_content, history_text, citizen_name, is_current_sent, has_unreplied)
        
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
    result = generate_suggested_reply_with_evidence(
        email_content=email_content, 
        email_subject=email_subject, 
        sender=sender,
        category="General",
        attachment_content="",
        history=[]
    )
    return result.get("suggested_reply", "Error generating reply")
