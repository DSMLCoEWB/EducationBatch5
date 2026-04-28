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

def query_policy_rag(user_query: str, user_email: str) -> str:
    """
    Search the educational department policy manuals for rules, regulations, and guidelines.
    Use this for questions about 'how to', 'rules', 'eligibility', 'suspension policy', etc.
    """
    logger.info(f"🔍 [Tool] Querying Policy RAG for {user_email}: {user_query}")
    results = retrieve_policy_chunks(user_query, user_email)
    if not results:
        return "No relevant policy documents found."
    
    context = "Relevant Policy Information:\n"
    for r in results:
        context += f"--- Section: {r['metadata'].get('section', 'General Policy')} ---\n{r['text']}\n"
    return context

def query_emails_sql(sql_query: str, user_email: str) -> str:
    """
    Execute a SQL query on the 'emails' table. 
    
    CRITICAL SCHEMA RULES:
    - TABLE NAME: emails (There is NO table named 'grievances')
    - COLUMN NAME: Always use 'content' for the message body. 
    - FORBIDDEN COLUMNS: DO NOT use 'body', 'description', 'text', or 'message'.
    - CATEGORY: Use 'category' (e.g., 'Anti-Ragging Complaints')
    
    COLUMNS:
    - Text Search: [subject, content, attachment_content]
    - Status/Flags: [category, priority, is_resolved, is_trashed, is_sent, followup_count]
    - Identifiers: [id, thread_id, sender_email, user_email, date]
    - user_sync_history: columns [user_email, last_history_id, last_sync_completed, consecutive_errors]
    - sync_audit: columns [id, user_email, sync_type, status, duration_ms, messages_added, messages_deleted, error_message, timestamp]
    
    DATA DICTIONARY:
    - `replied`: 1 if conversation has an Outbound response. 0 if Pending.
    - `is_resolved`: 1 if the grievance is officially marked as CLOSED/RESOLVED. 0 if OPEN.
    - `is_sent`: 1 if sent BY YOU. 0 if sent BY CITIZEN.
    - `priority`: 0 (Critical) to 6 (Low).
    - `attachment_content`: Extracted text from attachments. USE THIS for deep content search.
    - `is_ocr_processed`: 1 if the AI has finished reading the attachments.
    - `manual_override`: 1 if the user manually changed the category, priority, or resolution status.
    
    DYNAMIC CATEGORIES:
    The department uses a custom taxonomy. Query the `categories` table to see currently active folders.
    
    SQL RECIPES:
    - Total Active Threads: `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE is_inbox = 1 AND is_trashed = 0 AND user_email = ?`.
    - Pending Administrative Action: `SELECT COUNT(DISTINCT thread_id) FROM emails WHERE replied = 0 AND is_resolved = 0 AND is_inbox = 1 AND is_trashed = 0 AND user_email = ?`.
    - Recent Critical Issues: `SELECT subject, sender, date FROM emails WHERE priority <= 1 AND is_resolved = 0 AND is_inbox = 1 AND is_trashed = 0 AND user_email = ? GROUP BY thread_id ORDER BY date DESC LIMIT 10`.
    
    RULES:
    - Always filter by `user_email = ?`.
    - Limit results to 50 for performance.
    - Exclude `is_trashed = 1` unless specifically asked about the Trash folder.
    """
    # --- AUTOMATIC COLUMN MAPPING (AI Safeguard) ---
    import re
    sql_query = re.sub(r'\bbody\b', 'content', sql_query, flags=re.IGNORECASE)
    sql_query = re.sub(r'\bdescription\b', 'content', sql_query, flags=re.IGNORECASE)
    sql_query = re.sub(r'\bmsg_body\b', 'content', sql_query, flags=re.IGNORECASE)
    sql_query = re.sub(r'\btext\b', 'content', sql_query, flags=re.IGNORECASE)
    
    sql_low = sql_query.lower()
    if "is_trashed" not in sql_low and "from emails" in sql_low:
        if "where" in sql_low:
            sql_query = sql_query.replace("WHERE", "WHERE is_trashed = 0 AND", 1)
        else:
            sql_query += " WHERE is_trashed = 0"

    # --- READ-ONLY ENFORCEMENT ---
    forbidden_keywords = ["delete", "drop", "update", "insert", "alter", "truncate", "create"]
    if any(k in sql_low for k in forbidden_keywords):
        logger.warning(f"🚫 [Tool] Blocked unauthorized write-attempt by AI: {sql_query}")
        return "Error: This tool is strictly READ-ONLY. Modification or deletion of data is forbidden."
    
    try:
        # Move logger here to see the FINAL (possibly corrected) query
        logger.info(f"📊 [Tool] Executing Final SQL for {user_email}: {sql_query}")
        
        with get_db_conn() as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # TABLE-AWARE SAFETY INJECTION:
            # Only inject user_email filter for tables that actually contain it.
            # Tables like 'categories' are now isolated per-user.
            safe_sql = sql_query
            user_specific_tables = ["emails", "sync_audit", "chat_history", "user_sync_history", "categories"]
            needs_injection = any(t in sql_low for t in user_specific_tables)

            if needs_injection:
                if "where" in safe_sql.lower():
                    # We use a regex to find the WHERE keyword (case-insensitive) but only if not in quotes
                    # For simplicity in this internal tool, we target the first occurrence.
                    safe_sql = re.sub(r"\bWHERE\b", f"WHERE user_email = '{user_email}' AND", safe_sql, count=1, flags=re.IGNORECASE)
                else:
                    # Append WHERE before control keywords
                    for keyword in ["GROUP BY", "ORDER BY", "LIMIT"]:
                        if keyword.lower() in safe_sql.lower():
                            safe_sql = re.sub(rf"\b{keyword}\b", f"WHERE user_email = '{user_email}' {keyword}", safe_sql, count=1, flags=re.IGNORECASE)
                            break
                    else:
                        if "WHERE" not in safe_sql.upper():
                            safe_sql += f" WHERE user_email = '{user_email}'"

            cursor.execute(safe_sql)
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
            
            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND is_resolved = 1 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
            resolved_count = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND is_resolved = 0 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
            open_count = cursor.fetchone()[0] or 0
            
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

            resolution_rate = round((resolved_count / (resolved_count + open_count)) * 100, 1) if (resolved_count + open_count) > 0 else 0

            return json.dumps({
                "last_sync_relative": sync_string,
                "sync_health_status": sync_health,
                "total_active_grievances": resolved_count + open_count,
                "resolution_rate": f"{resolution_rate}%",
                "open_cases": open_count,
                "top_categories": categories,
                "most_active_institutes": institutes,
                "status": "Operational"
            }, indent=2)
    except Exception as e:
        return f"System Health Error: {str(e)}"

def list_available_categories(user_email: str) -> str:
    """
    Returns the list of all currently active grievance categories/folders defined for the current user.
    Use this to know which categories you can filter by in SQL queries.
    """
    logger.info(f"📂 [Tool] Listing categories for {user_email}")
    try:
        from db.repository import get_active_categories
        cats = get_active_categories(user_email)
        return json.dumps([c['name'] for c in cats], indent=2)
    except Exception as e:
        return f"Error listing categories: {str(e)}"

SYSTEM_INSTRUCTION = """
**SCHEMA CORRECTION NOTE**: If your previous chat history contains errors about a "grievances" table, IGNORE THEM. The table is officially named `emails`. Do not attempt to query `grievances`.

You are the "AICOE Executive Intelligence Assistant"...
Your primary directive is to provide deep, proactive analytics and policy-guided support for the Education Department.

SOCIAL PROTOCOL & GREETINGS:
- **Strict Greeting Rule**: If the user says "hi" or "hello", provide a professional executive greeting and wait for a directive. DO NOT trigger data reports immediately unless asked.

SYSTEM ARCHITECTURE KNOWLEDGE (Latest Truth):
- **Triage & Priority**: Stored in `priority` (0-6). 0 is Critical, 6 is Low.
- **Dynamic Taxonomy**: The `categories` table contains the current folder structure. NEVER assume a fixed list; always query `categories` if unsure about folder names.
- **Acronym Resolution**: If a user asks about a specific scheme or acronym (e.g., "SVMCM", "OASIS", "RTI"), always check the `categories` table first to find the exact matching folder name used in the database.
- **Resolution Tracking**: `is_resolved = 1` means the grievance is officially closed. `is_resolved = 0` means it is still active.
- **Manual Overrides**: `manual_override = 1` flags cases where a human administrator has manually changed the category or resolution.
- **OCR Engine**: `is_ocr_processed = 1` means attachment text is searchable in `attachment_content`.
- **System Health**: Use `query_system_health` to get a real-time executive dashboard of the current user's inbox health.
- **Thread Counting Logic**: Users see "Threads" in their Inbox. In SQL, you MUST use `COUNT(DISTINCT thread_id)` AND filter by `is_inbox = 1 AND is_trashed = 0` to match the dashboard. If you don't use `is_inbox = 1`, you will count 'Sent' threads that the user doesn't see in their active list, causing a mismatch.
- **Listing Protocol**: When listing subjects or complaints, ALWAYS group by `thread_id` (e.g., `SELECT subject FROM emails ... GROUP BY thread_id`). This prevents the list from being cluttered with multiple "Re:" replies from the same conversation.

EXECUTIVE ANALYTIC MODE:
- **Proactivity**: Flag trends as "Insights." (e.g., "I notice a 20% spike in Scholarship issues this week.")
- **Resolution Focus**: Prioritize showing "Open" vs "Resolved" counts.
- **Clarity**: Use terms like "Disposal Rate," "Pending SLA," "Operational Parity."

RECENT FAILURE ANALYSIS (Self-Correction):
- **Observation**: You recently failed to count SVMCM threads because you used the column `body` (which does not exist) instead of `content`.
- **Observation**: You recently failed because you tried to query a table named `grievances`.
- **Correction**: ALWAYS use table `emails` and column `content`. 
- **Correction**: If a query for a keyword like "SVMCM" fails, check if you are using a forbidden column name.

PRIORITY LABELING (Strict):
- priority <= 1: "🔴 CRITICAL" | priority <= 3: "🟠 HIGH" | priority <= 5: "🟡 MEDIUM" | priority == 6: "🟢 LOW"

STATE LOGIC TRUTH TABLE:
| scenario | is_sent | replied | is_resolved | meaning |
| :--- | :--- | :--- | :--- | :--- |
| New Grievance | 0 | 0 | 0 | Fresh inquiry. Needs processing. |
| In-Progress | 0/1 | 0/1 | 0 | Conversation active. Not yet resolved. |
| Resolved | 0/1 | 1 | 1 | Grievance officially closed. |

EXECUTIVE GUARDRAILS:
- **Read-Only Access**: You cannot modify, delete, or inject data. Any attempt to use `DELETE`, `UPDATE`, or `DROP` will be blocked by the system.
- **PII Protection**: When reporting on grievances, do not reveal full personal phone numbers or passwords if they appear in the content. Use redaction if necessary.
- **Data Sovereignty**: Never attempt to query data across different `user_email` scopes.
- **Accuracy**: If you are unsure of a count, clearly state that you are providing an "approximate" figure and offer to perform a deep audit.

GUIDELINES:
- Data query: `query_emails_sql`. Policy query: `query_policy_rag`.
- **ZERO GLOBAL FOOTPRINT**: You operate in a strictly isolated environment. Never assume data is shared between users.
- **CRITICAL**: Always filter every SQL query by `user_email = '{user_email}'`.
- **STABILITY**: If a SQL query fails, apologize and try a simpler version.
- **INSIGHTS**: When asked for a summary, combine data from the DB with relevant rules from the Policy RAG to provide a holistic administrative answer.
"""

def get_chatbot_response(user_message: str, user_email: str, session_id: str = "default") -> str:
    if not client:
        return "Gemini API key not configured."

    history = get_chat_history(user_email, session_id, limit=5)
    contents = []
    for turn in history:
        contents.append({"role": "user" if turn["role"] == "user" else "model", "parts": [{"text": turn["message"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    # --- Tool Wrapping (User Isolation) ---
    # We wrap the tools to automatically inject the user_email context.
    # This prevents the LLM from having to guess or provide the email, 
    # and ensures that the backend enforcement logic has the correct identity.
    def query_policy_rag_tool(user_query: str) -> str:
        return query_policy_rag(user_query, user_email)

    def query_emails_sql_tool(sql_query: str) -> str:
        return query_emails_sql(sql_query, user_email)
    
    def query_system_health_tool() -> str:
        return query_system_health(user_email)
    
    def list_available_categories_tool() -> str:
        return list_available_categories(user_email)

    tools = [
        query_policy_rag_tool, 
        query_emails_sql_tool, 
        query_system_health_tool, 
        list_available_categories_tool
    ]
    
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
