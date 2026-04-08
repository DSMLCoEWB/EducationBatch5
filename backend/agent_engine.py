import os
import sqlite3
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from rag.retriever import retrieve_policy_chunks
from database_api import save_chat_message, get_chat_history
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
    - emails: columns [id, sender, subject, content, category, mail_type, priority, date, is_demo, is_trashed, is_inbox, user_email]
    SCHEMA DEFINITIONS:
    - 'Inbox': Always use `is_inbox = 1 AND is_trashed = 0`.
    - 'Trash': Use `is_trashed = 1`. DO NOT query this unless the user specifically asks for 'deleted' or 'trashed' items.
    - CRITICAL: Every query for grievances, counts, or lists MUST include `is_trashed = 0` to avoid inaccuracies.
    - 'Mail Type': Only has values 'Fresh' or 'Follow-up'.
    - 'Category': e.g., 'Suspension', 'FIR', 'Semester', 'Admissions', 'Miscellaneous'.
    - 'User Email': Always filter by the current `user_email` provided in the tool call context if asked about 'my' emails.
    - ALWAYS use 'LIKE' for text searches (e.g., WHERE sender LIKE '%pune%').
    - Limit results to 10 for performance.
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
        return json.dumps(results[:10], indent=2)
    except Exception as e:
        return f"Database Error: {str(e)}"

# --- AGENT LOGIC ---

SYSTEM_INSTRUCTION = """
You are the "AICOE Education Department Assistant", a premium AI chatbot designed to help administration and citizens with grievance management.
Your tone is professional, helpful, and data-driven.

You have access to two primary tools:
1. `query_policy_rag`: Use this to answer questions about rules, policies, and procedural guidelines.
2. `query_grievances_db`: Use this to query the actual database of emails and grievances for statistics and tracking.

GUIDELINES:
- If a user asks a general question, answer it directly.
- If a user asks about data (numbers, status, specific emails), use `query_grievances_db`.
- If a user asks about rules or how things work, use `query_policy_rag`.
- You can combine tools if needed (e.g., "What is the suspension policy AND how many suspension cases do we have?").
- Always format your final response using Markdown. Use bolding, bullet points, and tables where appropriate to look 'premium'.
- If you cite a policy, mention the Section title provided in the tool output.
- Avoid technical jargon about SQL or RAG in your final response to the user.
- If you don't know the answer, even after using tools, say so politely.
- DATA INTEGRITY: By default, you only represent active grievances. Never include items where `is_trashed = 1` in your counts or summaries unless the user explicitly mentions "Trash" or "Deleted".
- USER CONTEXT: If a user asks about "my" emails, ALWAYS filter by the current logged-in `user_email`.
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
    
    tools = [query_policy_rag, query_grievances_db]
    
    try:
        # Use automatic tool calling with multi-model fallback
        response = generate_content_with_fallback(
            client=client,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools,
            ),
            model_list=ULTIMATE_FALLBACK_LIST,
            label="Chatbot"
        )
        
        if not response:
            return "I am currently experiencing high demand and my primary models are at capacity. Please try again in a few moments."

        reply_text = getattr(response, "text", "") or ""
        
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
