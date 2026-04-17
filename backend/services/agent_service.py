import os
import json
from datetime import datetime
from google import genai
from google.genai import types
from typing import List, Dict, Any, Optional, Tuple

from config import (
    GOOGLE_API_KEY, CHATBOT_GEMINI_API_KEY, ULTIMATE_FALLBACK_LIST
)
from db.session import get_db_conn
from db.repository import save_chat_message, get_chat_history
from ai_utils import generate_content_with_fallback
from services.rag_service import retrieve_policy_chunks
from core.logging import get_logger

logger = get_logger("services.agent")

API_KEY = CHATBOT_GEMINI_API_KEY or GOOGLE_API_KEY
client = genai.Client(api_key=API_KEY) if API_KEY else None

# --- AGENT TOOLS ---

def query_policy_rag(user_query: str) -> str:
    """
    Search the educational department policy manuals for rules, regulations, and guidelines.
    Use this for questions about 'how to', 'rules', 'eligibility', 'suspension policy', etc.
    """
    logger.info(f"🔍 [Tool] Querying Policy RAG: {user_query}")
    results = retrieve_policy_chunks(user_query)
    if not results:
        return "No relevant policy documents found."
    
    context = "Relevant Policy Information:\n"
    for r in results:
        context += f"--- Section: {r['metadata'].get('section', 'General Policy')} ---\n{r['text']}\n"
    return context

def query_grievances_db(sql_query: str) -> str:
    """
    Execute a SQL query on the grievances database to get statistics or specific record details.
    
    TABLES:
    - emails: columns [id, gmail_id, thread_id, parent_email_id, sender, sender_email, recipient_email, subject, content, category, mail_type, priority, date, has_attachment, attachments, is_demo, replied, is_trashed, is_inbox, is_sent, is_priority_refined, is_ocr_processed, attachment_content, followup_count, institute_name, user_email, last_synced]
    - user_sync_history: columns [user_email, last_history_id, last_sync_completed, consecutive_errors]
    - sync_audit: columns [id, user_email, sync_type, status, duration_ms, messages_added, messages_deleted, error_message, timestamp]
    
    DATA DICTIONARY:
    - `replied`: 1 if conversation is Answered/Closed. 0 if Pending Action.
    - `is_sent`: 1 if sent BY YOU. 0 if sent BY CITIZEN.
    - `priority`: 0 (Critical) to 6 (Low).
    - `attachment_content`: Extracted text from attachments. USE THIS for deep content search.
    - `is_ocr_processed`: 1 if the AI has finished reading the attachments.
    - `is_priority_refined`: 1 if AI has validated the priority level.
    
    OFFICIAL CATEGORIES (16):
    - 'Suspension / Disciplinary', 'Legal Issues', 'RTI Matters', 'CMO Issues', 'Semester / Examination', 'Scholarship & Fee Concession', 'Purchase / Procurement Issues', 'Cash Issues', 'Anti-Ragging Complaints', 'Accreditation & Ranking', 'Service Matters', 'Appointment Issues', 'Transfer Cases', 'Inspection Matters', 'Seat Matrix Issues', or 'Miscellaneous'.
    
    SQL RECIPES:
    - Total Active Threads: `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE is_inbox = 1 AND is_trashed = 0 AND user_email = ?`.
    - Pending Action: `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE replied = 0 AND is_inbox = 1 AND is_trashed = 0 AND user_email = ?`.
    - Sync Health: `SELECT * FROM sync_audit WHERE user_email = ? ORDER BY timestamp DESC LIMIT 5`.
    
    RULES:
    - Always filter by `user_email = ?`.
    - Limit results to 50 for performance.
    """
    logger.info(f"📊 [Tool] Executing SQL: {sql_query}")
    
    # Programmatic Safety Filter: Force exclude trash if not explicitly requested
    sql_low = sql_query.lower()
    if "is_trashed" not in sql_low and "from emails" in sql_low:
        if "where" in sql_low:
            sql_query = sql_query.replace("WHERE", "WHERE is_trashed = 0 AND", 1)
        else:
            sql_query += " WHERE is_trashed = 0"

    try:
        with get_db_conn() as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            
            if not rows:
                return "No matching records found in the database."
            
            results = [dict(r) for r in rows[:50]]
            return json.dumps(results, indent=2)
    except Exception as e:
        return f"Database Error: {str(e)}"

def query_system_health(user_email: str) -> str:
    """
    Returns a high-level snapshot of the grievance system status, including sync health, 
    category distribution, and institutional activity.
    """
    logger.info(f"🚀 [Tool] Querying System Health: {user_email}")
    try:
        with get_db_conn() as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(last_synced) FROM emails WHERE user_email = ?", (user_email,))
            last_sync = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT category, COUNT(*) FROM emails 
                WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 
                GROUP BY category ORDER BY COUNT(*) DESC LIMIT 5
            """, (user_email,))
            categories = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor.execute("""
                SELECT institute_name, COUNT(*) FROM emails 
                WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 AND institute_name != 'Individual / Public'
                GROUP BY institute_name ORDER BY COUNT(*) DESC LIMIT 3
            """, (user_email,))
            institutes = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND replied = 0 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
            pending_count = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
            total_active_threads = cursor.fetchone()[0] or 0
            
            # Sync Audit
            cursor.execute("SELECT status, timestamp FROM sync_audit WHERE user_email = ? ORDER BY timestamp DESC LIMIT 1", (user_email,))
            audit = cursor.fetchone()
            sync_health = audit[0] if audit else "Unknown"

            # Relative time calculation
            sync_string = "Unknown"
            if last_sync:
                try:
                    last_sync_dt = datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
                    seconds_ago = (datetime.utcnow() - last_sync_dt).total_seconds()
                    if seconds_ago < 60: sync_string = "Just now"
                    elif seconds_ago < 3600: sync_string = f"{int(seconds_ago // 60)} minutes ago"
                    else: sync_string = f"{int(seconds_ago // 3600)} hours ago"
                except: sync_string = last_sync

            return json.dumps({
                "last_sync_relative": sync_string,
                "sync_health_status": sync_health,
                "total_active_grievances": total_active_threads,
                "pending_administrative_action": pending_count,
                "top_categories": categories,
                "most_active_institutes": institutes,
                "status": "Operational"
            }, indent=2)
    except Exception as e:
        return f"System Health Error: {str(e)}"

# --- SYSTEM INSTRUCTION ---

SYSTEM_INSTRUCTION = """
You are the "AICOE Executive Intelligence Assistant", the absolute maximum realization of an AI-driven administrative partner.
Your primary directive is to provide deep, proactive analytics and policy-guided support for the Education Department.

SOCIAL PROTOCOL & GREETINGS:
- **Strict Greeting Rule**: If the user says "hi" or "hello", provide a professional executive greeting and wait for a directive. DO NOT trigger data reports immediately unless asked.

SYSTEM ARCHITECTURE KNOWLEDGE (Latest Truth):
- **Triage & Priority**: Stored in `priority` (0-6). 0 is Critical, 6 is Low.
- **Refinement Status**: `is_priority_refined = 1` means AI has audited the category/priority.
- **OCR Engine**: `is_ocr_processed = 1` means attachment text is searchable in `attachment_content`.
- **Status Reconciliation**: `replied = 1` (Answered/Closed), `replied = 0` (Pending Action).

EXECUTIVE ANALYTIC MODE:
- **Proactivity**: Flag trends as "Insights."
- **Clarity**: Use terms like "Case Volume," "Pending SLA," "Operational Parity."

PRIORITY LABELING (Strict):
- priority <= 1: "🔴 CRITICAL" | priority <= 3: "🟠 HIGH" | priority <= 5: "🟡 MEDIUM" | priority == 6: "🟢 LOW"

ADMINISTRATIVE DOMAIN KNOWLEDGE:
- **CMO Issues**: High-priority escalations from Chief Minister Office.
- **RTI Matters**: Statutory Right to Information requests (Strict deadlines).
- **Scholarship**: Includes 'SVMCM' (Swami Vivekananda Merit-cum-Means) and 'Oasis'.
- **Service Matters**: Payroll/Seniority issues for teachers/staff.

STATE LOGIC TRUTH TABLE:
| scenario | is_sent | mail_type | replied | meaning |
| :--- | :--- | :--- | :--- | :--- |
| New Inquiry | 0 | 'Fresh' | 0 | New grievance. Needs response. |
| Follow-up | 0 | 'Follow-up' | 0 | Citizen reply. Needs attention. |
| Admin Response | 1 | 'Reply' | 1 | Case Resolved. |

GUIDELINES:
- Data query: `query_grievances_db`. Policy query: `query_policy_rag`.
- **CRITICAL**: Always filter every SQL query by `user_email = '{user_email}'`.
"""

def get_chatbot_response(user_message: str, user_email: str, session_id: str = "default") -> str:
    if not client:
        return "Gemini API key not configured."

    history = get_chat_history(user_email, session_id, limit=5)
    contents = []
    for turn in history:
        contents.append({"role": "user" if turn["role"] == "user" else "model", "parts": [{"text": turn["message"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    tools = [query_policy_rag, query_grievances_db, query_system_health]
    
    try:
        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION.format(user_email=user_email),
                tools=tools,
            ),
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Agent"
        )
        
        reply_text = ""
        try:
            reply_text = response.text
        except:
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    reply_text = " ".join([p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text])

        reply_text = reply_text.strip() if reply_text else "Analysis complete. How can I facilitate your administrative decision-making further?"
        
        save_chat_message(user_email, session_id, "user", user_message)
        save_chat_message(user_email, session_id, "assistant", reply_text)
        
        return reply_text
    except Exception as e:
        logger.error(f"❌ Agent Error: {e}")
        return f"Error: {str(e)}"
