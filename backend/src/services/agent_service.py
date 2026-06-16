import os
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent  # type: ignore
from langgraph.errors import GraphRecursionError
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

from config import (
    GOOGLE_API_KEY, CHATBOT_GEMINI_API_KEY, ULTIMATE_FALLBACK_LIST, AI_PREFER_LOCAL, PRIMARY_LOCAL_MODEL
)
from db.session import get_db_conn
from db.repository import save_chat_message, get_chat_history
from services.ai_utils import generate_content_with_fallback, get_genai_client
from services.rag_service import retrieve_policy_chunks
from core.logging import get_logger

logger = get_logger("services.agent")

def extract_json_block(text: str) -> Optional[str]:
    # Find the first opening brace
    start = text.find("{")
    if start == -1:
        return None
        
    brace_count = 0
    in_string = False
    escape = False
    
    for i in range(start, len(text)):
        char = text[i]
        
        if char == '"' and not escape:
            in_string = not in_string
        elif char == '\\' and in_string:
            escape = not escape
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start:i+1]
                    
        escape = False
    return None

class CustomChatOllama(BaseChatModel):
    model_name: str
    tools: Optional[List[Any]] = None
    
    @property
    def _llm_type(self) -> str:
        return "ollama-custom"
        
    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:  # type: ignore
        self.tools = tools
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        from services.ai_utils import ollama_client
        import uuid
        
        # Translate messages
        ollama_msgs = []
        for msg in messages:
            role = ""
            if isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, ToolMessage):
                role = "tool"
            else:
                role = "user"
            
            ollama_msg: Dict[str, Any] = {"role": role, "content": str(msg.content)}
            
            if role == "assistant" and getattr(msg, "tool_calls", None):
                tcs = []
                for tc in getattr(msg, "tool_calls", []):
                    tcs.append({
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["args"]
                        }
                    })
                ollama_msg["tool_calls"] = tcs
                
            if role == "tool":
                ollama_msg["name"] = getattr(msg, "name", "")
                
            ollama_msgs.append(ollama_msg)
            
        ollama_tools = []
        if self.tools:
            for t in self.tools:
                props = {}
                for name, info in t.args.items():
                    props[name] = {
                        "type": info.get("type", "string"),
                        "description": info.get("description", "")
                    }
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": {
                            "type": "object",
                            "properties": props,
                            "required": list(t.args.keys())
                        }
                    }
                })
                
        # Call Ollama Client
        context_size = int(os.getenv("OLLAMA_CONTEXT_LENGTH", 4096))
        options = {
            "num_ctx": context_size,
            "temperature": 0.2
        }
        
        try:
            response = ollama_client.chat(
                model=self.model_name,
                messages=ollama_msgs,
                tools=ollama_tools if ollama_tools else None,
                options=options
            )
        except Exception as e:
            raise RuntimeError(f"Ollama chat error: {e}")
            
        resp_msg = getattr(response, "message", None) or response.get("message", {})
        
        # Safely extract content
        if hasattr(resp_msg, "content"):
            content = resp_msg.content or ""
        else:
            content = resp_msg.get("content", "") or ""
            
        lc_tool_calls = []
        raw_tool_calls = getattr(resp_msg, "tool_calls", None) or resp_msg.get("tool_calls", [])
        if raw_tool_calls:
            for tc in raw_tool_calls:
                func = getattr(tc, "function", None) or tc.get("function", {})
                func_name = getattr(func, "name", None) or func.get("name")
                func_args = getattr(func, "arguments", None) or func.get("arguments")
                if func_name:
                    lc_tool_calls.append({
                        "name": func_name,
                        "args": func_args or {},
                        "id": str(uuid.uuid4())
                    })
                    
        # --- RECOVERY GUARD FOR LOCAL MODELS ---
        # If the local model wrote the JSON tool call directly into the text content,
        # extract it and translate it back to a structured LangChain tool call.
        if not lc_tool_calls and "{" in content:
            try:
                json_str = extract_json_block(content)
                if json_str:
                    # Fix invalid JSON escape sequences hallucinated by local models
                    json_str = json_str.replace('\\%', '%')
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        name = data.get("name") or data.get("function", {}).get("name")
                        args = data.get("parameters") or data.get("arguments") or data.get("function", {}).get("arguments")
                        if name:
                            lc_tool_calls.append({
                                "name": name,
                                "args": args or {},
                                "id": str(uuid.uuid4())
                            })
                            # Strip the JSON block and any hallucinated text/results generated after it
                            json_start_idx = content.find(json_str)
                            content = content[:json_start_idx].strip()
            except Exception:
                pass
                
        ai_msg = AIMessage(
            content=content,
            tool_calls=lc_tool_calls
        )
        
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

API_KEY = CHATBOT_GEMINI_API_KEY or GOOGLE_API_KEY

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

def translate_json_to_sql(obj: dict) -> str:
    # Compile a structured JSON query representation into a SQL string
    table = obj.get("table") or "emails"
    fields = obj.get("fields") or obj.get("select") or "*"
    if isinstance(fields, list):
        fields = ", ".join(fields)
        
    sql = f"SELECT {fields} FROM {table}"
    
    conditions = []
    
    # Check for specific filter keys
    col = obj.get("column") or obj.get("filter_column")
    val = obj.get("filter") or obj.get("value") or obj.get("keyword")
    
    if col and val:
        conditions.append(f"{col} LIKE '%{val}%'")
    elif val:
        conditions.append(f"(subject LIKE '%{val}%' OR content LIKE '%{val}%')")
        
    # Check if there is an explicit where clause
    where = obj.get("where") or obj.get("condition")
    if where:
        if isinstance(where, dict):
            for k, v in where.items():
                if isinstance(v, str):
                    conditions.append(f"{k} = '{v}'")
                else:
                    conditions.append(f"{k} = {v}")
        elif isinstance(where, str):
            conditions.append(where)
            
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
        
    return sql

def query_emails_sql(sql_query: Any, user_email: str) -> str:
    """
    Execute a SQL query on the 'emails' table. 
    
    CRITICAL SCHEMA RULES:
    - TABLE NAME: emails (There is NO table named 'grievances')
    - COLUMN NAME: Always use 'content' for the message body. 
    - FORBIDDEN COLUMNS: DO NOT use 'body', 'description', 'text', or 'message'.
    - CATEGORY: Use 'category' (e.g., 'Anti-Ragging Complaints')
    
    COLUMNS:
    - emails (Text Search): [subject, content, attachment_content, institute_name, html_content]
    - emails (Status/Flags): [category, priority, is_resolved, is_trashed, is_inbox, is_sent, replied, has_attachment, is_ocr_processed, manual_override, is_priority_refined, is_demo]
    - emails (Identifiers): [id, thread_id, gmail_id, parent_email_id, sender, sender_email, recipient_email, user_email, date, last_synced, followup_count, mail_type, attachments, sync_interval_seconds]
    - user_sync_history: columns [user_email, last_history_id, last_sync_completed, consecutive_errors, sync_interval_seconds, interval_updated_at]
    - sync_audit: columns [id, user_email, sync_type, status, duration_ms, messages_added, messages_deleted, error_message, timestamp]
    - categories: columns [id, name, color, icon, is_active, user_email]
    - chat_history: columns [id, user_email, session_id, role, message, timestamp]
    - revoked_sessions: columns [user_email, revoked_at, reason]
    - priority_rules: columns [priority, user_email, label, keywords, description]
    
    DATA DICTIONARY:
    - `replied`: 1 if conversation has an Outbound response. 0 if Pending.
    - `is_resolved`: 1 if the grievance is officially marked as CLOSED/RESOLVED. 0 if OPEN.
    - `is_sent`: 1 if sent BY YOU. 0 if sent BY CITIZEN.
    - `priority`: 0 (Critical) to 3 (Low).
    - `attachment_content`: Extracted text from attachments. USE THIS for deep content search.
    - `is_ocr_processed`: 1 if the AI has finished reading the attachments.
    - `manual_override`: 1 if the user manually changed the category, priority, or resolution status.
    
    DYNAMIC CATEGORIES:
    The department uses a custom taxonomy. Query the `categories` table to see currently active folders.
    
    CRITICAL RULE: FOR ALL STATUS COUNTS AND DASHBOARD STATS, YOU MUST USE `v_threads`.
    
    SCHEMA:
    1. `v_threads` (View) [PRIMARY FOR STATS]: Unified grievance data (LATEST email per thread). 
       - Columns: status ('fresh', 'ongoing', or 'resolved'), thread_id, mail_type, category, priority, subject, content, is_trashed, last_message_date.
    2. `emails` (Table) [AUDIT ONLY]: Raw email data. Use for deep message-level audits, finding specific IDs, or verifying metadata.
       - Columns: id, thread_id, gmail_id, sender_email, recipient_email, subject, content, date, category, mail_type, priority, is_resolved, replied, manual_override, is_trashed, is_inbox, is_sent, has_attachment, institute_name.
    
    GOLDEN SQL EXAMPLES:
    - Count Statuses (Keyword): `SELECT COALESCE(SUM(CASE WHEN status = 'fresh' THEN 1 ELSE 0 END), 0) as fresh, COALESCE(SUM(CASE WHEN status = 'ongoing' THEN 1 ELSE 0 END), 0) as ongoing FROM v_threads WHERE user_email = ? AND (subject LIKE '%SVMCM%' OR content LIKE '%SVMCM%') AND is_trashed = 0`
    - Breakdown by status: `SELECT status, count(*) FROM v_threads WHERE user_email = ? AND is_trashed = 0 GROUP BY status`
    - List emails by topic (e.g. ragging): `SELECT thread_id, subject FROM v_threads WHERE user_email = ? AND is_trashed = 0 AND (category ILIKE '%ragging%' OR subject ILIKE '%ragging%' OR content ILIKE '%ragging%' OR content ILIKE '%hazing%' OR content ILIKE '%bullying%' OR attachment_content ILIKE '%ragging%' OR attachment_content ILIKE '%hazing%' OR attachment_content ILIKE '%bullying%')` -- ALWAYS INCLUDE RELEVANT SYNONYMS FOR ALL TEXT FIELDS!
    
    RULES:
    - ALWAYS filter by `user_email = ?`.
    - ALWAYS filter by `is_trashed = 0`.
    - Use `v_threads` for all dashboard-level counts/stats.
    - NEVER display raw `thread_id` or `gmail_id` to the user. They are ugly Microsoft Graph/Gmail IDs that break the UI. Keep them internal and just refer to the subject or a short summary.
    """
    # --- JSON COMPLIANCE & TRANSLATION ---
    if isinstance(sql_query, dict):
        try:
            sql_query = translate_json_to_sql(sql_query)
        except Exception:
            pass
    elif isinstance(sql_query, str) and sql_query.strip().startswith("{"):
        try:
            data = json.loads(sql_query)
            if isinstance(data, dict):
                sql_query = translate_json_to_sql(data)
        except Exception:
            pass

    if not isinstance(sql_query, str):
        sql_query = str(sql_query)
        
    # Fix AI unnecessarily escaping percent signs in LIKE clauses
    sql_query = sql_query.replace('\\%', '%')

    sql_low = sql_query.lower()
    
    # --- INDUSTRY-STANDARD CORRECTION GUARD ---
    is_stats_query = any(k in sql_low for k in ["count(", "sum(", "group by"])
    # Detect any attempt to MANUALLY calculate grievance state on the raw table
    grievance_raw_cols = ["is_resolved", "replied", "manual_override"]
    is_raw_stat_attempt = is_stats_query and any(col in sql_low for col in grievance_raw_cols)
    
    if is_raw_stat_attempt and "from emails" in sql_low:
        logger.warning(f"⚠️ [Correction Guard] AI attempted raw status calculation on emails table.")
        return "ERROR: Do not manually calculate 'Resolved/Ongoing' logic using raw columns on the 'emails' table. You MUST query the 'v_threads' view and use its 'status' column for all grievance-state analytics."
    
    if "is_trashed" not in sql_low and ("from emails" in sql_low or "from v_threads" in sql_low):
        logger.warning(f"⚠️ [Correction Guard] AI forgot is_trashed filter.")
        return "ERROR: Every query must explicitly include 'is_trashed = 0' (or 1 if searching trash). Please correct your SQL and try again."

    # --- READ-ONLY ENFORCEMENT ---
    # We strip string literals (anything inside quotes) before checking for keywords to prevent 
    # false positives. For example, searching for "student drop-out" shouldn't trigger the "DROP" blocker.
    sql_no_strings = re.sub(r"'.*?'", "", sql_low)
    sql_no_strings = re.sub(r'".*?"', "", sql_no_strings)
    
    forbidden_keywords = [r"\bdelete\b", r"\bdrop\b", r"\bupdate\b", r"\binsert\b", r"\balter\b", r"\btruncate\b", r"\bcreate\b"]
    for k in forbidden_keywords:
        if re.search(k, sql_no_strings):
            logger.warning(f"🚫 [Tool] Blocked unauthorized write-attempt by AI: {sql_query}")
            return "Error: This tool is strictly READ-ONLY. Modification or deletion of data is forbidden."
    
    try:
        # Move logger here to see the FINAL (possibly corrected) query
        logger.info(f"📊 [Tool] Executing Final SQL for {user_email}: {sql_query}")
        
        with get_db_conn(tenant_email=user_email) as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row  # type: ignore
            cursor = conn.cursor()
            
            # TABLE-AWARE SAFETY INJECTION:
            # Only inject user_email filter for tables that actually contain it.
            # Tables like 'categories' are now isolated per-user.
            safe_sql = sql_query
            user_specific_tables = ["emails", "sync_audit", "chat_history", "user_sync_history", "categories", "priority_rules"]
            needs_injection = any(t in sql_low for t in user_specific_tables)
            safe_email = user_email.replace("'", "''")

            if needs_injection:
                if "where" in safe_sql.lower():
                    # We use a regex to find the WHERE keyword (case-insensitive) but only if not in quotes
                    # For simplicity in this internal tool, we target the first occurrence.
                    safe_sql = re.sub(r"\bWHERE\b", f"WHERE user_email = '{safe_email}' AND", safe_sql, count=1, flags=re.IGNORECASE)
                else:
                    # Append WHERE before control keywords
                    for keyword in ["GROUP BY", "ORDER BY", "LIMIT"]:
                        if keyword.lower() in safe_sql.lower():
                            safe_sql = re.sub(rf"\b{keyword}\b", f"WHERE user_email = '{safe_email}' {keyword}", safe_sql, count=1, flags=re.IGNORECASE)
                            break
                    else:
                        if "WHERE" not in safe_sql.upper():
                            safe_sql += f" WHERE user_email = '{safe_email}'"

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
        with get_db_conn(tenant_email=user_email) as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row  # type: ignore
            cursor = conn.cursor()
            
            cursor.execute("SELECT MAX(last_synced) FROM emails WHERE user_email = ?", (user_email,))
            last_sync = cursor.fetchone()[0]  # type: ignore
            sync_string = "Never"
            if last_sync:
                try:
                    # Robust ISO parsing
                    sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                    now_tz = datetime.now(sync_dt.tzinfo)
                    diff = now_tz - sync_dt
                    mins = int(diff.total_seconds() / 60)
                    if mins < 1: sync_string = "Just now"
                    elif mins < 60: sync_string = f"{mins} minutes ago"
                    else: sync_string = f"{mins // 60} hours ago"
                except:
                    sync_string = last_sync
            
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
            
            # --- DASHBOARD KPI ENGINE (Synchronized with v_threads) ---
            # 1. Total Unique Conversations
            cursor.execute("SELECT COUNT(*) FROM v_threads WHERE user_email = ?", (user_email,))
            total_convs = cursor.fetchone()[0] or 0  # type: ignore

            # 2. Unresolved Threads
            cursor.execute("""
                SELECT COUNT(*) FROM v_threads
                WHERE user_email = ? AND
                ((manual_override = 1 AND is_resolved = 0) 
                 OR (COALESCE(manual_override, 0) = 0 AND replied = 0 AND is_resolved = 0))
            """, (user_email,))
            unresolved_count = cursor.fetchone()[0] or 0  # type: ignore

            # 3. Resolved/Actioned Threads
            resolved_count = total_convs - unresolved_count

            # 4. Fresh Threads
            cursor.execute("""
                SELECT COUNT(*) FROM v_threads
                WHERE user_email = ? AND mail_type = 'fresh'
                AND ((manual_override = 1 AND is_resolved = 0) 
                  OR (COALESCE(manual_override, 0) = 0 AND replied = 0 AND is_resolved = 0))
            """, (user_email,))
            fresh_threads = cursor.fetchone()[0] or 0  # type: ignore

            # 5. Ongoing Threads
            cursor.execute("""
                SELECT COUNT(*) FROM v_threads
                WHERE user_email = ? AND mail_type = 'follow-up'
                AND ((manual_override = 1 AND is_resolved = 0) 
                  OR (COALESCE(manual_override, 0) = 0 AND replied = 0 AND is_resolved = 0))
            """, (user_email,))
            ongoing_threads = cursor.fetchone()[0] or 0  # type: ignore

            # 6. Avg Pending Duration
            cursor.execute("""
                SELECT last_message_date FROM v_threads
                WHERE user_email = ? AND
                ((manual_override = 1 AND is_resolved = 0) 
                  OR (COALESCE(manual_override, 0) = 0 AND replied = 0 AND is_resolved = 0))
            """, (user_email,))
            pending_dates = cursor.fetchall()
            avg_days_str = "0 days"
            if pending_dates:
                total_days = 0
                now = datetime.now() # Use local now if tz-naive, or handle tz
                for row in pending_dates:
                    try:
                        # Try ISO first, fallback to old format
                        date_str = row[0]
                        try:
                            d = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        except:
                            d = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                        
                        # Match frontend: Math.ceil(diffTime / day)
                        # We must ensure both are tz-aware or both tz-naive
                        if d.tzinfo:
                            now_tz = datetime.now(d.tzinfo)
                            diff_sec = (now_tz - d).total_seconds()
                        else:
                            diff_sec = (datetime.now() - d).total_seconds()
                            
                        days = math.ceil(diff_sec / (24 * 3600))
                        total_days += max(0, days)
                    except: pass
                
                avg_days = round(total_days / len(pending_dates))
                if avg_days == 0: avg_days_str = "< 1 day"
                elif avg_days == 1: avg_days_str = "1 day"
                else: avg_days_str = f"{avg_days} days"

            # 7. Attachments Count (Threads with attachments)
            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM emails WHERE user_email = ? AND has_attachment = 1 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
            attachment_threads = cursor.fetchone()[0] or 0  # type: ignore

            # 8. Activity Volume (Last 7 Days)
            activity_volume = []
            for i in range(6, -1, -1):
                day = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).strftime("%Y-%m-%d")
                cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND date LIKE ?", (user_email, f"{day}%"))
                activity_volume.append({"date": day, "count": cursor.fetchone()[0] or 0})  # type: ignore

            # Sync Audit
            cursor.execute("SELECT status, timestamp FROM sync_audit WHERE user_email = ? ORDER BY timestamp DESC LIMIT 1", (user_email,))
            audit = cursor.fetchone()
            sync_health = audit[0] if audit else "Unknown"

            logger.info(f"📊 [Health] Results: Total={total_convs} Unresolved={unresolved_count} Resolved={resolved_count} Fresh={fresh_threads} Ongoing={ongoing_threads}")

            # Build category summary (top 5)
            top_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info(f"📊 [Health] Results: Total={total_convs} Unresolved={unresolved_count} Resolved={resolved_count} Fresh={fresh_threads} Ongoing={ongoing_threads}")

            return json.dumps({
                "dashboard_kpis": {
                    "total_conversations": total_convs,
                    "unresolved": unresolved_count,
                    "resolved": resolved_count,
                    "avg_pending_duration": avg_days_str,
                    "fresh_threads": fresh_threads,
                    "ongoing_threads": ongoing_threads,
                    "threads_with_attachments": attachment_threads
                },
                "category_distribution": categories,
                "top_institutes": institutes,
                "activity_volume_7d": activity_volume,
                "sync_status": {
                    "last_sync": sync_string,
                    "health": sync_health
                },
                "status": "Operational"
            }, indent=2, default=str)
    except Exception as e:
        logger.error(f"❌ [Health] System health query FAILED: {str(e)}", exc_info=True)
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

def get_thread_narrative(user_email: str, thread_id: str) -> str:
    """Fetches the full chronological history of a conversation thread."""
    logger.info(f"🧵 [Tool] Fetching thread narrative: {thread_id} for {user_email}")
    try:
        with get_db_conn(tenant_email=user_email) as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row  # type: ignore
            cursor = conn.cursor()
            cursor.execute("""
                SELECT date, sender, sender_email, content, is_sent, mail_type 
                FROM emails 
                WHERE user_email = ? AND thread_id = ? AND is_trashed = 0
                ORDER BY date ASC
            """, (user_email, thread_id))
            rows = cursor.fetchall()
            
            if not rows:
                return f"No messages found for thread {thread_id}."
            
            narrative = f"--- Conversation History for Thread: {thread_id} ---\n\n"
            for row in rows:
                role = "DEPARTMENT (You)" if row['is_sent'] else f"CITIZEN ({row['sender']})"
                narrative += f"DATE: {row['date']}\nFROM: {role} [{row['sender_email']}]\nTYPE: {row['mail_type'].upper()}\nMESSAGE:\n{row['content']}\n"
                narrative += "-" * 30 + "\n"
            
            return narrative
    except Exception as e:
        return f"Error fetching thread: {str(e)}"

def get_attachment_text(user_email: str, email_id: str) -> str:
    """Retrieves the OCR-extracted text from an email's attachments."""
    logger.info(f"📄 [Tool] Reading attachments for email: {email_id}")
    try:
        with get_db_conn(tenant_email=user_email) as conn:
            import sqlite3
            conn.row_factory = sqlite3.Row  # type: ignore
            cursor = conn.cursor()
            cursor.execute("""
                SELECT subject, attachment_content, is_ocr_processed 
                FROM emails 
                WHERE user_email = ? AND id = ?
            """, (user_email, email_id))
            row = cursor.fetchone()
            
            if not row:
                return "Email not found."
            if not row['attachment_content']:
                return "This email has no attachments or no text could be extracted."
            
            status = " [OCR COMPLETE]" if row['is_ocr_processed'] else " [OCR PENDING]"
            return f"--- Attachment Content for: {row['subject']}{status} ---\n\n{row['attachment_content']}"
    except Exception as e:
        return f"Error reading attachments: {str(e)}"

SYSTEM_INSTRUCTION = """
**SCHEMA CORRECTION NOTE**: If your previous chat history contains errors about a "grievances" table, IGNORE THEM. The table is officially named `emails`. Do not attempt to query `grievances`.

You are the "AICOE Executive Intelligence Assistant"...
Your primary directive is to provide deep, proactive analytics and policy-guided support for the {custom_role}.

TEMPORAL AWARENESS:
- **Current Date & Time**: {current_datetime} (IST, Asia/Kolkata).
- Use this for all time-relative queries like "today", "this week", "last 7 days", etc.

SOCIAL PROTOCOL & GREETINGS:
- **Strict Greeting Rule**: If the user says "hi" or "hello", provide a professional executive greeting and wait for a directive. DO NOT trigger data reports immediately unless asked.

SYSTEM ARCHITECTURE KNOWLEDGE (Latest Truth):
- **Triage & Priority**: Stored in `priority` (0-3). 0 is Critical, 3 is Low.
- **Dynamic Taxonomy**: The `categories` table contains the current folder structure. NEVER assume a fixed list; always query `categories` if unsure about folder names.
- **Acronym Resolution**: If a user asks about a specific scheme or acronym (e.g., "SVMCM", "OASIS", "RTI"), always check the `categories` table first to find the exact matching folder name used in the database.
- **Resolution Tracking**: `is_resolved = 1` means the grievance is officially closed. `is_resolved = 0` means it is still active.
- **Manual Overrides**: `manual_override = 1` flags cases where a human administrator has manually changed the category or resolution.
- **OCR Engine**: `is_ocr_processed = 1` means attachment text is searchable in `attachment_content`.
- **System Health**: Use `system_health_tool` to get ALL dashboard KPIs in one call. It returns total conversations, unresolved, resolved, fresh, ongoing, avg pending duration, category distribution, and 7-day activity. **Do NOT re-query these numbers with SQL afterwards — trust the tool output.**
- **Priority Rules**: Dynamic triage configurations are stored in `priority_rules`. Tier rules have `priority` (0 to 3), and custom global escalation & guardrail instructions are stored under `priority = -1` (label = 'Global Rules'). You can read this table to understand the user's custom urgency triggers or tone constraints.
- **Thread Counting Logic**: Users see "Threads" in their Inbox. In SQL, you MUST use `COUNT(DISTINCT thread_id)` AND filter by `is_inbox = 1 AND is_trashed = 0` to match the dashboard. If you don't use `is_inbox = 1`, you will count 'Sent' threads that the user doesn't see in their active list, causing a mismatch.
- **Dashboard Parity (Actioned State)**: If the latest message in a thread was sent by the department (`is_sent = 1`), the frontend displays it as **Low (3)** regardless of its internal priority. This is the "Actioned" state. For ANY counting, listing, or reporting of active grievances, you MUST treat these Actioned threads as Low (3) and exclude them from counts of "Pending" or "Active" work, as the user perceives them as already handled.
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

DASHBOARD ACCURACY (MANDATORY):
- To provide figures that match the Executive Dashboard, you MUST query the `v_threads` view.
- Use the `status` column in `v_threads` to distinguish between 'fresh', 'ongoing', and 'resolved' cases. 
- Do NOT attempt to calculate resolution states manually on the raw `emails` table.

PRIORITY LABELING:
- priority == 0: "🔴 CRITICAL" | priority == 1: "🟠 HIGH" | priority == 2: "🟡 MEDIUM" | priority == 3: "🟢 LOW"

EXECUTIVE GUARDRAILS:
- **Read-Only Access**: You cannot modify, delete, or inject data. Any attempt to use `DELETE`, `UPDATE`, or `DROP` will be blocked by the system.
- **PII Protection**: When reporting on grievances, do not reveal full personal phone numbers or passwords if they appear in the content. Use redaction if necessary.
- **Data Sovereignty**: Never attempt to query data across different `user_email` scopes.
- **Accuracy**: If you are unsure of a count, clearly state that you are providing an "approximate" figure and offer to perform a deep audit.
- **Off-Topic Queries**: You are strictly bound to the context of the {custom_role}, grievance management, and institutional policies. If a user asks you about general knowledge, programming, entertainment, or anything outside of your specialized domain, you MUST politely refuse to answer and remind them of your purpose.

GUIDELINES:
- Data query: `emails_sql_tool`. Policy query: `policy_rag_tool`.
- **ZERO GLOBAL FOOTPRINT**: You operate in a strictly isolated environment. Never assume data is shared between users.
- **CRITICAL**: Always filter every SQL query by `user_email = '{user_email}'`.
- **STABILITY**: If a SQL query fails, apologize and try a simpler version.
- **INSIGHTS**: When asked for a summary, combine data from the DB with relevant rules from the Policy RAG to provide a holistic administrative answer.
"""

def get_chatbot_response(user_message: str, user_email: str, session_id: str = "default") -> str:
    # --- RESOURCE LOCK ---
    # Claim the hardware for the human interaction
    from core.resource_manager import AI_RESOURCE_MANAGER
    AI_RESOURCE_MANAGER.acquire_high_priority()

    # Allow local execution even without a Gemini API key

    # OPTIMIZATION: Reduced history limit from 5 to 3 to save tokens and latency
    history = get_chat_history(user_email, session_id, limit=3)
    
    # Map to LangChain messages
    messages = []
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["message"]))
        else:
            messages.append(AIMessage(content=turn["message"]))
    messages.append(HumanMessage(content=user_message))
    
    # --- Tool Wrapping (User Isolation) ---
    # We inject user_email automatically to prevent hallucination and maintain absolute multi-tenant security
    @tool
    def policy_rag_tool(user_query: str) -> str:
        """Search the educational department policy manuals for rules, regulations, and guidelines. Use this for questions about 'how to', 'rules', 'eligibility', 'suspension policy', etc."""
        return query_policy_rag(user_query, user_email)

    @tool
    def emails_sql_tool(sql_query: str) -> str:
        """Execute a SQL query on the 'emails' table. MUST use table 'emails' and column 'content'."""
        return query_emails_sql(sql_query, user_email)

    @tool
    def system_health_tool() -> str:
        """Returns ALL dashboard KPIs in a single call: total conversations, unresolved, resolved, fresh threads, ongoing threads, avg pending duration, category distribution, and 7-day activity volume. Use this FIRST for any dashboard or stats question. Do NOT run additional SQL to re-verify these numbers."""
        return query_system_health(user_email)

    @tool
    def available_categories_tool() -> str:
        """Returns the list of all currently active grievance categories/folders."""
        return list_available_categories(user_email)

    @tool
    def thread_narrative_tool(thread_id: str) -> str:
        """
        Fetches the full chronological conversation history of a specific thread. 
        Use this when you need to understand the context of a long-running grievance or dispute.
        """
        return get_thread_narrative(user_email, thread_id)

    @tool
    def attachment_explorer_tool(email_id: str) -> str:
        """
        Retrieves the extracted OCR text from an email's attachments (PDFs/Images).
        Use this when the user asks about specific details inside an attached document.
        """
        return get_attachment_text(user_email, email_id)

    tools = [
        policy_rag_tool, 
        emails_sql_tool, 
        system_health_tool, 
        available_categories_tool,
        thread_narrative_tool,
        attachment_explorer_tool
    ]
    
    # Iterate through the fallback list to ensure high availability
    if not ULTIMATE_FALLBACK_LIST:
        return "System configuration error: No AI models defined."
        
    for raw_model_name in ULTIMATE_FALLBACK_LIST:
        is_ollama = raw_model_name.startswith("ollama/") or "ollama" in raw_model_name.lower()
        
        # Enforce AI_PREFER_LOCAL choice
        if AI_PREFER_LOCAL:
            if not is_ollama:
                continue
        else:
            if is_ollama:
                continue
                
        model_name = raw_model_name.replace("models/", "").replace("ollama/", "")
        try:
            if is_ollama:
                # Initialize local Ollama Chat model
                # Note: We use model_name from the fallback list because the chatbot requires tool-calling support
                # which may not be available on all models (e.g. gemma3:4b does not support tools in Ollama).
                llm = CustomChatOllama(model_name=model_name)
            else:
                # Dynamic Enterprise Routing for LangChain Chatbot
                from config import VERTEX_AI_PROJECT, VERTEX_AI_LOCATION
                if VERTEX_AI_PROJECT:
                    try:
                        from langchain_google_vertexai import ChatVertexAI
                        logger.info(f"🔒 Initializing Enterprise Vertex AI Chatbot (Project: {VERTEX_AI_PROJECT})")
                        llm = ChatVertexAI(
                            model_name=model_name,
                            project=VERTEX_AI_PROJECT,
                            location=VERTEX_AI_LOCATION,
                            temperature=0.2
                        )
                    except ImportError:
                        logger.error("❌ langchain-google-vertexai not installed but VERTEX_AI_PROJECT is configured. Enterprise privacy cannot be guaranteed.")
                        raise RuntimeError("Strict Enterprise Privacy Mode failed: langchain-google-vertexai is missing.")
                else:
                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=API_KEY,
                        temperature=0.2
                    )
            
            from db.repository import get_system_role
            custom_role = get_system_role(user_email)

            # Create LangGraph ReAct Agent Loop
            agent = create_react_agent(  # type: ignore
                model=llm,
                tools=tools,
                prompt=SYSTEM_INSTRUCTION.format(
                    user_email=user_email,
                    current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"),
                    custom_role=custom_role
                )
            )
            
            # Invoke the stateful graph. Limit allows up to ~6 tool calls + final answer.
            result = agent.invoke(
                {"messages": messages}, 
                config={"recursion_limit": 15}
            )
            
            # Extract the final answer
            final_message = result["messages"][-1]
            raw_content = final_message.content
            
            if isinstance(raw_content, list):
                # Handle multimodal/structured outputs where content is a list of blocks
                text_parts = [str(block.get("text", block)) if isinstance(block, dict) else str(block) for block in raw_content]
                reply_text = " ".join(text_parts).strip()
            else:
                reply_text = str(raw_content).strip() if raw_content else "Analysis complete."
            
            # Persist to database
            save_chat_message(user_email, session_id, "user", user_message)
            save_chat_message(user_email, session_id, "assistant", reply_text)
            
            return reply_text
            
        except GraphRecursionError:
            logger.error(f"❌ [Agent] Model {model_name} got stuck in a reasoning loop.")
            return "I am having trouble processing this complex request right now. Could you please rephrase it or be more specific?"
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "quota" in err_msg or "not found" in err_msg or "obsolete" in err_msg or "400" in err_msg:
                logger.warning(f"🕒 [Agent] Model {model_name} failed ({e}). Trying next...")
                continue
            else:
                logger.warning(f"⚠️ [Agent] Model {model_name} encountered an error: {e}")
                continue
                
    logger.error("❌ Agent Error: All models in fallback list failed.")
    return "Error: All configured AI models failed to respond. Please check your API quotas."
