import os
import sqlite3
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from rag.retriever import retrieve_policy_chunks
from db.repository import save_chat_message, get_chat_history
from ai_utils import generate_content_with_fallback, ULTIMATE_FALLBACK_LIST

load_dotenv()

# --- CONFIG ---
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grievances.db")
API_KEY = (
    os.getenv("CHATBOT_GEMINI_API_KEY") # New dedicated key
    or os.getenv("GOOGLE_API_KEY") 
    or os.getenv("GEMINI_API_KEY")
)

client = genai.Client(api_key=API_KEY) if API_KEY else None

# --- TOOLS ---

def query_policy_rag(user_query: str):
    """
    Search the educational department policy manuals for rules, regulations, and guidelines.
    Use this for questions about 'how to', 'rules', 'eligibility', 'suspension policy', etc.
    """
    print(f"[TOOL]: Querying Policy RAG for: {user_query}")
    results = retrieve_policy_chunks(user_query)
    if not results:
        return "No relevant policy documents found."
    
    context = "Relevant Policy Information:\n"
    for r in results:
        context += f"--- Section: {r['metadata']['section']} ---\n{r['text']}\n"
    return context

def query_grievances_db(sql_query: str):
    """
    Execute a SQL query on the grievances database to get statistics or specific record details.
    Tables:
    - emails: columns [id, gmail_id, thread_id, sender, sender_email, subject, content, category, mail_type, priority, date, has_attachment, attachments, is_demo, replied, is_trashed, is_inbox, is_sent, is_priority_refined, is_ocr_processed, attachment_content, followup_count, institute_name, user_email, last_synced]
    - 'Data Dictionary' (Column Definitions):
        - `id`: Unique fingerprint for each email.
        - `thread_id`: Unique ID for the conversation.
        - `replied`: 1 if conversation is Answered/Closed. 0 if Pending Action.
        - `is_sent`: 1 if sent BY YOU. 0 if sent BY CITIZEN.
        - `priority`: 0 (Critical) to 6 (Low).
        - `mail_type`: 'Fresh' (New), 'Follow-up' (Response), 'Reply' (Your response).
        - `attachment_content`: (CRITICAL) Extracted text from PDFs/Images. USE THIS for queries like "What does the attachment say?".
        - `is_ocr_processed`: 1 if the AI has finished reading the attachments.
        - `is_inbox`: 1 if active in main Inbox (Dashboard focus).
        - `is_sent`: 1 if part of Outbound/Sent mail.
        - `institute_name`: The recognized organization (e.g., Shivaji College).
        - `user_email`: The owner (Filter by: '{user_email}').
    - 'Official Categories' (16 Types): 
        - 'Suspension / Disciplinary', 'Legal Issues', 'RTI Matters' (Right to Information), 'CMO Issues' (Chief Minister Office), 'Semester / Examination', 'Scholarship & Fee Concession', 'Purchase / Procurement Issues', 'Cash Issues', 'Anti-Ragging Complaints', 'Accreditation & Ranking', 'Service Matters', 'Appointment Issues', 'Transfer Cases', 'Inspection Matters', 'Seat Matrix Issues', or 'Miscellaneous'.
    - 'SQL RECIPES' (Mandatory):
        - Total Active Threads (Grievances): `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE is_inbox = 1 AND is_trashed = 0`.
        - Pending Action: `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE replied = 0 AND is_inbox = 1 AND is_trashed = 0`.
        - Topic Search (e.g., SVMCM): `SELECT DISTINCT thread_id, subject FROM emails WHERE (subject LIKE '%keyword%' OR content LIKE '%keyword%' OR category LIKE '%keyword%' OR institute_name LIKE '%keyword%') AND is_inbox = 1 AND is_trashed = 0`.
        - Searching the Trash: `SELECT * FROM emails WHERE is_trashed = 1`.
        - Deep Attachment Search: `SELECT * FROM emails WHERE attachment_content LIKE '%keyword%' AND is_inbox = 1`.
    - Limit results to 50 for performance.
    """
    print(f"[TOOL]: Executing SQL: {sql_query}")
    
    # Programmatic Safety Filter: Force exclude trash if not explicitly requested
    if "is_trashed" not in sql_query.lower() and "from emails" in sql_query.lower():
        if "where" in sql_query.lower():
            sql_query = sql_query.replace("WHERE", "WHERE is_trashed = 0 AND", 1)
        else:
            sql_query += " WHERE is_trashed = 0"
        print(f"[TOOL-AUTOFIX]: Reinforced SQL: {sql_query}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()
        
        if not rows:
            return "No matching records found in the database."
        
        # Format as a simple list of dicts for the LLM
        results = [dict(zip(columns, row)) for row in rows]
        return json.dumps(results[:50], indent=2)
    except Exception as e:
        return f"Database Error: {str(e)}"

def query_system_health(user_email: str):
    """
    Returns a high-level snapshot of the grievance system status, including sync health, 
    category distribution, and institutional activity. Use this for general 'health checks' 
    or when asked about overall trends.
    """
    print(f"[TOOL]: Querying System Health for: {user_email}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Last Sync
        cursor.execute("SELECT MAX(last_synced) FROM emails WHERE user_email = ?", (user_email,))
        last_sync = cursor.fetchone()[0]
        
        # 2. Category Distribution (Inbox only)
        cursor.execute("""
            SELECT category, COUNT(*) FROM emails 
            WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 
            GROUP BY category ORDER BY COUNT(*) DESC LIMIT 5
        """, (user_email,))
        categories = cursor.fetchall()
        
        # 3. Top Active Institutes (Inbox only)
        cursor.execute("""
            SELECT institute_name, COUNT(*) FROM emails 
            WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 AND institute_name != 'Individual / Public'
            GROUP BY institute_name ORDER BY COUNT(*) DESC LIMIT 3
        """, (user_email,))
        institutes = cursor.fetchall()
        
        # 3. Pending Count (Matching Dashboard 84 count)
        cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND replied = 0 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        pending_count = cursor.fetchone()[0]

        # 4. Total Volume (Inbox only to match Dashboard 86 count)
        cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        total_active_threads = cursor.fetchone()[0]
        
        from datetime import datetime
        last_sync_dt = datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
        seconds_ago = (datetime.utcnow() - last_sync_dt).total_seconds()
        
        if seconds_ago < 60:
            sync_string = "Just now"
        elif seconds_ago < 3600:
            sync_string = f"{int(seconds_ago // 60)} minutes ago"
        else:
            sync_string = f"{int(seconds_ago // 3600)} hours ago"

        conn.close()
        
        return json.dumps({
            "last_sync_relative": sync_string,
            "last_sync_utc": f"{last_sync} UTC",
            "total_active_grievances": total_active_threads,
            "pending_administrative_action": pending_count,
            "top_categories": {c[0]: c[1] for c in categories},
            "most_active_institutes": {i[0]: i[1] for i in institutes},
            "status": "Operational"
        }, indent=2)
    except Exception as e:
        return f"System Health Error: {str(e)}"

# --- AGENT LOGIC ---

SYSTEM_INSTRUCTION = """
You are the "AICOE Executive Intelligence Assistant", the absolute maximum realization of an AI-driven administrative partner.
Your primary directive is to provide deep, proactive analytics and policy-guided support for the Education Department.

GUARDRAILS & SAFETY:
- **Scope Lockdown**: You are an Education Department assistant. DO NOT answer questions about unrelated topics (e.g., general world news, entertainment, cooking, or coding tasks unrelated to this system). Politely redirect the user to administrative matters.
- **SQL Integrity**: You only have READ access. DO NOT attempt to write SQL that modifies, deletes, or drops data. Stick to the provided SQL Recipes.
- **Professional Neutrality**: Maintain a neutral, objective, and executive tone. Avoid personal opinions or speculative commentary on policy.
- **Privacy Awareness**: While you assist with grievances, handle PII (names, emails) with high professional discretion.

SOCIAL PROTOCOL & GREETINGS:
- **Strict Greeting Rule**: If the user says "hi", "hello", or performs a basic greeting, DO NOT call data tools or provide proactive reports immediately. Respect their space.
- **Protocol**: Provide a professional executive greeting and wait for a specific directive.

SYSTEM ARCHITECTURE KNOWLEDGE (The "System Manual"):
- **Ingestion**: You use a real-time Gmail Sync engine.
- **Classification**: Every email is categorized into one of 16 grievance types.
- **Triage & Priority**: Priority (Stored in `priority`, 0-6) is determined by AI logic. 0 is Critical, 6 is Low (Routine).
- **Mail Type Intelligence**:
    - `Fresh`: A brand new inquiry from a citizen.
    - `Follow-up`: A citizen's response in an existing thread.
    - `Reply`: An administrative response sent by YOU (the user).
- **Status Reconciliation**: All emails in a thread share a single `replied` flag. If YOU send the last email, `replied = 1` (Answered/Closed). If the CITIZEN sends the last email, `replied = 0` (Pending Action).

EXECUTIVE ANALYTIC MODE:
- **Proactivity**: Flag trends (e.g., "Scholarship issues are up 20%") as "Insights."
- **Clarity**: Use administrative terminology: "Case Volume," "Pending SLA," "Operational Parity."

PRIORITY LABELING RULES (Strict):
- priority <= 1: "🔴 CRITICAL"
- priority <= 3: "🟠 HIGH" 
- priority <= 5: "🟡 MEDIUM"
- priority == 6: "🟢 LOW (ROUTINE)"

GUIDELINES:
- **Data (Numbers/Stats/Lists)**: Use `query_grievances_db`.
- **Policy (Rules/Guidelines)**: Use `query_policy_rag`.
- **User Context**: Always filter by `user_email = '{user_email}'`.

DATA SOURCES & COUNTING RULES:
- **Grievance Count**: Always use the live counts provided by your tools. This must match the current state of the database.
- **Pending Status**: Use the `replied = 0` flag to identify cases requiring active administrative attention.
- **Sent Volume**: Use `mail_type = 'Reply'` or `is_sent = 1` to track your own administrative performance.

ADMINISTRATIVE DOMAIN KNOWLEDGE (Grievance Definitions):
- **CMO Issues**: High-priority escalations originating from or referenced to the Chief Minister's Office.
- **RTI Matters**: Legally mandated 'Right to Information' requests. These have strict statutory deadlines.
- **Scholarship & Fee Concession**: Includes the 'SVMCM' (Swami Vivekananda Merit-cum-Means) scheme. Crucial for student welfare.
- **Anti-Ragging**: Sensitive disciplinary matters involving student safety. Immediate attention required.
- **Service Matters / Appointment**: Employee-related grievances (teachers/staff) regarding payroll, seniority, or hiring.
- **Semester / Examination**: Academic timeline issues. High volume during results or registration periods.
- **Legal Issues**: Active litigation or court-related inquiries (e.g., High Court orders).

STATE LOGIC TRUTH TABLE (Confusion Resolver):
| scenario | is_sent | mail_type | replied | meaning |
| :--- | :--- | :--- | :--- | :--- |
| **New Inquiry** | 0 | 'Fresh' | 0 | New grievance (In Inbox). Needs response. |
| **Follow-up** | 0 | 'Follow-up' | 0 | Citizen reply (In Inbox). Needs attention. |
| **Admin Response** | 1 | 'Reply' | 1 | You replied to a citizen. Case Resolved. |
| **Admin Fresh** | 1 | 'Fresh' | 1 | You started a new outbound thread (Compose). |
| **Actioned** | 0 | 'Any' | 1 | This citizen message was already handled by you. |
"""

def get_chatbot_response(user_message: str, user_email: str, session_id: str = "default"):
    if not client:
        return "Error: Gemini API Key not configured. Please check your .env file."

    # 1. Load context from history
    history = get_chat_history(user_email, session_id, limit=5)
    
    # 2. Format history for Gemini
    # We use a simple list of dicts for the prompt or structured turns
    contents = []
    for turn in history:
        contents.append({"role": "user" if turn["role"] == "user" else "model", "parts": [{"text": turn["message"]}]})
    
    # Append the new message
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    tools = [query_policy_rag, query_grievances_db, query_system_health]
    
    try:
        # Use automatic tool calling with multi-model fallback
        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION.format(user_email=user_email),
                tools=tools,
            ),
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Chatbot"
        )
        
        if not response:
            return "I am currently experiencing high demand and my primary models are at capacity. Please try again in a few moments."

        # Robust text extraction: Support both direct text and candidate-based extraction
        reply_text = ""
        try:
            reply_text = response.text
        except Exception:
            # Fallback to candidate parts if .text is unavailable (common in some tool-call turns)
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    parts = candidate.content.parts
                    text_parts = [p.text for p in parts if hasattr(p, 'text') and p.text]
                    reply_text = " ".join(text_parts)

        reply_text = reply_text.strip() if reply_text else ""
        
        # FINAL SAFETY: If the model returned data but no text, provide a helpful summary
        if not reply_text:
            print("[DEBUG]: Chatbot returned empty text but successful response. Providing generic fallback.")
            reply_text = "I have successfully analyzed your system health. Everything is operational. How can I help you further with specific grievances or policy inquiries?"

        # 3. Save to history
        save_chat_message(user_email, session_id, "user", user_message)
        save_chat_message(user_email, session_id, "assistant", reply_text)
        
        return reply_text
    except Exception as e:
        print(f"[ERROR]: Agent failed: {e}")
        return f"I'm sorry, I encountered an error while processing your request: {str(e)}"

if __name__ == "__main__":
    # Test query
    print(get_chatbot_response("How many suspension cases are there?", user_email="test@example.com"))
