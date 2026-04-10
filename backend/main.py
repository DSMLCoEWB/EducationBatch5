import email
import base64
from itertools import count
import os
import sqlite3
import pandas as pd
from database_api import init_db, save_emails_batch, get_emails_from_db, mark_as_trashed, delete_all_for_user, get_existing_gmail_ids, update_email_attachment_content, DB_PATH, reclassify_all_stored_emails
import re
import json
import ast
import requests
import jwt
import hashlib
import hmac
import base64
import json
from datetime import datetime
from datetime import datetime, timedelta
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional, Set
from email_parser import parse_eml, ATTACHMENTS_DIR, extract_attachment_text, extract_text_from_attachment_ai
from classifier import classify_grievance
from followup import detect_followup
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from chatbot import ask
from agent_engine import get_chatbot_response
from priority_llm import get_llm_priority, get_batch_priorities, apply_thread_escalation
from pydantic import BaseModel
from rag.reply_generator import generate_suggested_reply_with_evidence
from rag.retriever import reload_retriever_data, get_embedder
from rag_pipeline.ingest import ingest_policy_document, CHUNKS_PATH, INDEX_PATH
import logging
import faiss
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from cryptography.fernet import Fernet, InvalidToken
from google import genai
load_dotenv()

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FILES_DIR = "./files"
EXCEL_FILE = "./data/grievances.xlsx"
POLICY_DIR = Path(__file__).parent / "policies"
POLICY_DIR.mkdir(parents=True, exist_ok=True)
DEMO_EMAILS_PATH = Path(__file__).parent / "demo_emails_from_chunks.json"
DEMO_POLICY_DIR = Path(__file__).parent / "demo_policies"
DEMO_POLICY_DIR.mkdir(parents=True, exist_ok=True)

# dynamic email fetch configuration
EMAIL_SOURCE_MODE = "dynamic"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "your-project@gmail.com").strip()
DYNAMIC_FETCH_LIMIT = int(os.getenv("DYNAMIC_FETCH_LIMIT", "0"))
DYNAMIC_AUTO_REFRESH_SECONDS = int(os.getenv("DYNAMIC_AUTO_REFRESH_SECONDS", "30"))
DEMO_USE_LLM_PRIORITY = os.getenv("DEMO_USE_LLM_PRIORITY", "false").strip().lower() == "true"
DYNAMIC_USE_LLM_PRIORITY = os.getenv("DYNAMIC_USE_LLM_PRIORITY", "false").strip().lower() == "true"

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback").strip()
GOOGLE_OAUTH_TOKEN_PATH = Path(os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(Path(__file__).parent / "data" / "google_oauth_token.enc")))
GOOGLE_OAUTH_TOKENS_DIR = Path(os.getenv("GOOGLE_OAUTH_TOKENS_DIR", str(Path(__file__).parent / "data" / "oauth_tokens")))
GOOGLE_OAUTH_ENCRYPTION_KEY = os.getenv("GOOGLE_OAUTH_ENCRYPTION_KEY", "").strip()
GOOGLE_OAUTH_COOKIE_SECURE = os.getenv("GOOGLE_OAUTH_COOKIE_SECURE", "false").strip().lower() == "true"
GOOGLE_OAUTH_SUCCESS_REDIRECT_URL = os.getenv("GOOGLE_OAUTH_SUCCESS_REDIRECT_URL", "").strip()
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/userinfo.profile",
]

_user_display_name_cache: Dict[str, str] = {}

SEEDED_SUBJECT_PREFIX = "[AICOE-SEED]"
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", GOOGLE_OAUTH_ENCRYPTION_KEY).strip()

_dynamic_cache_df_by_user: Dict[str, pd.DataFrame] = {}
_dynamic_cache_at_by_user: Dict[str, datetime] = {}
_is_syncing_by_user: Dict[str, bool] = {} # user_email -> bool
_user_locks: Dict[str, threading.Lock] = {}
_user_locks_main_lock = threading.Lock()

def _get_user_lock(user_email: str) -> threading.Lock:
    """Returns a thread-safe lock unique to each user_email."""
    key = _user_key(user_email)
    with _user_locks_main_lock:
        if key not in _user_locks:
            _user_locks[key] = threading.Lock()
        return _user_locks[key]
_priority_llm_worker_running_by_user: Dict[str, bool] = {}
_priority_llm_last_run_by_user: Dict[str, datetime] = {}
_priority_llm_consecutive_failures_by_user: Dict[str, int] = {}
_priority_llm_scored_ids_by_user: Dict[str, set[str]] = {}


def _get_google_fernet() -> Fernet:
    if not GOOGLE_OAUTH_ENCRYPTION_KEY:
        raise ValueError("GOOGLE_OAUTH_ENCRYPTION_KEY is required for secure OAuth token storage.")
    return Fernet(GOOGLE_OAUTH_ENCRYPTION_KEY.encode("utf-8"))


def _origin_is_secure_https(origin: str) -> bool:
    parsed = urlparse(origin)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_localhost_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def _validate_runtime_configuration() -> None:
    if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET or not GOOGLE_OAUTH_REDIRECT_URI:
        raise RuntimeError(
            "Missing Google OAuth configuration. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI."
        )
    if not GOOGLE_OAUTH_ENCRYPTION_KEY:
        raise RuntimeError("Missing GOOGLE_OAUTH_ENCRYPTION_KEY for secure token storage.")
    if not APP_SESSION_SECRET:
        raise RuntimeError("Missing APP_SESSION_SECRET for user session signing.")

    if IS_PRODUCTION:
        if not GOOGLE_OAUTH_COOKIE_SECURE:
            raise RuntimeError("GOOGLE_OAUTH_COOKIE_SECURE must be true in production.")
        if not GOOGLE_OAUTH_SUCCESS_REDIRECT_URL:
            raise RuntimeError("GOOGLE_OAUTH_SUCCESS_REDIRECT_URL is required in production.")
        if not _origin_is_secure_https(GOOGLE_OAUTH_SUCCESS_REDIRECT_URL):
            raise RuntimeError("GOOGLE_OAUTH_SUCCESS_REDIRECT_URL must use https in production.")
        insecure_origins = [origin for origin in cors_origins if not _origin_is_secure_https(origin) or _is_localhost_origin(origin)]
        if insecure_origins:
            raise RuntimeError(f"CORS_ORIGINS contains insecure origins for production: {insecure_origins}")

# Load college database
COLLEGES_DB = []
try:
    colleges_path = Path(__file__).parent / "data" / "colleges.json"
    with open(colleges_path, 'r', encoding='utf-8') as f:
        COLLEGES_DB = json.load(f)
    print(f"Loaded {len(COLLEGES_DB)} colleges from database")
except Exception as e:
    print(f"Warning: Could not load colleges database: {e}")

COLUMNS = [
    "email_id", "parent_email_id", "sender", "subject",
    "category", "mail_type", "followup_count","priority",
    "date", "content", "attachments", "attachment_content", "eml_file"
]

def clean_for_excel(text):
    """Remove illegal characters that Excel cannot handle"""
    if not isinstance(text, str):
        return text
    # Remove control characters (0x00-0x1F) except tab, newline, carriage return
    return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', text)


def _generate_email_id(content: str) -> str:
    # Strip common Gmail metadata symbols to ensure In-Reply-To matches the original ID
    clean = str(content or "").strip().lower().replace("<", "").replace(">", "")
    return hashlib.md5(clean.encode("utf-8")).hexdigest()[:12]


def _heuristic_priority(text: str, subject: str) -> int:
    text_lower = f"{subject} {text}".lower()
    if any(k in text_lower for k in ["chief secretary", "secretary higher education", "court order", "legal notice"]):
        return 1
    if any(k in text_lower for k in ["fir", "arrest", "police", "misconduct", "suspension", "disciplinary"]):
        return 2
    if any(k in text_lower for k in ["salary", "fund release", "increment", "arrear"]):
        return 4
    if any(k in text_lower for k in ["exam", "result", "admission", "deadline", "correction", "scholarship"]):
        return 5
    return 6


def _load_demo_emails() -> list[Dict[str, Any]]:
    if not DEMO_EMAILS_PATH.exists():
        raise FileNotFoundError(f"Missing demo email source: {DEMO_EMAILS_PATH}")

    with open(DEMO_EMAILS_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError("demo_emails_from_chunks.json must contain a list of email objects")

    return payload


def _build_demo_dataframe() -> pd.DataFrame:
    demo_emails = _load_demo_emails()
    df = pd.DataFrame()
    base_date = datetime.now() - timedelta(days=max(len(demo_emails), 1))

    for i, item in enumerate(demo_emails):
        subject = str(item.get("subject", "")).strip()
        body = str(item.get("body", "")).strip()
        if not subject and not body:
            continue

        content = f"{subject}\n{body}".strip()
        email_id = _generate_email_id(content)
        email_date = (base_date + timedelta(days=i)).date().isoformat()
        institute_name = COLLEGES_DB[i % len(COLLEGES_DB)] if COLLEGES_DB else "Unknown Institute"

        sender_name = "Grievance Applicant"
        sender_email = f"demo_applicant_{i + 1}@example.edu"

        category = classify_grievance(content)

        base_priority = _heuristic_priority(content, subject)

        mock_email_obj = {
            "email_id": email_id,
            "parent_email_id": "",
            "sender": sender_name,
            "subject": subject,
            "content": content,
            "date": email_date,
        }

        mail_type, parent_id, followup_count = detect_followup(mock_email_obj, df)
        final_priority = apply_thread_escalation(base_priority, followup_count)
        if final_priority is None:
            final_priority = base_priority

        row = {
            "email_id": email_id,
            "parent_email_id": parent_id or "",
            "sender": sender_name,
            "sender_email": sender_email,
            "institute_name": institute_name,
            "subject": subject,
            "category": category,
            "mail_type": mail_type,
            "followup_count": followup_count,
            "priority": int(final_priority),
            "date": email_date,
            "content": content,
            "attachments": "[]",
            "eml_file": f"demo_{i + 1}.eml",
            "is_demo": True,
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    return df


def _build_files_dataframe() -> pd.DataFrame:
    if not os.path.isdir(FILES_DIR):
        return pd.DataFrame(columns=COLUMNS)

    eml_files = [f for f in os.listdir(FILES_DIR) if f.endswith(".eml")]
    total_files = len(eml_files)
    processed = 0
    df = pd.DataFrame(columns=COLUMNS)

    print(f"📧 Found {total_files} email files to process...")

    for file in eml_files:
        processed += 1
        print(f"[{processed}/{total_files}] Processing: {file}")

        parsed_email = parse_eml(os.path.join(FILES_DIR, file))
        if parsed_email is None:
            print(f"⚠️ Skipping {file} (parse error)")
            continue

        if not df.empty and parsed_email["email_id"] in df["email_id"].values:
            print("✓ Already processed")
            continue

        category = classify_grievance(
            parsed_email["content"],
            subject=parsed_email.get("subject", ""),
            attachment_content=parsed_email.get("attachment_content", "")
        )
        mail_type, _, followup_count = detect_followup(parsed_email, df)

        base_priority = _heuristic_priority(parsed_email.get("content", ""), parsed_email.get("subject", ""))

        final_priority = apply_thread_escalation(base_priority, followup_count)
        if final_priority is None:
            final_priority = base_priority

        row = {
            **parsed_email,
            "category": category,
            "mail_type": mail_type,
            "followup_count": followup_count,
            "priority": final_priority,
            "date": parsed_email.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "is_demo": False,
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        print("✓ Added to database")

    return df


def _decode_header_value(raw_value: str | None) -> str:
    if not raw_value:
        return ""
    try:
        return str(make_header(decode_header(raw_value))).strip()
    except Exception:
        return str(raw_value).strip()


def _extract_email_body(msg: email.message.Message, gmail_id: str | None = None) -> str:
    import re
    html_parts: list[str] = []
    text_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disposition:
                continue
                
            payload = part.get_payload(decode=True)
            if not payload:
                continue
                
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            
            if content_type == "text/html":
                if gmail_id:
                    # Replace inline cid tags with a token the frontend can replace
                    decoded = re.sub(r'cid:([^\s\'"]+)', f'__API_BASE_URL__/api/emails/attachments/inline/{gmail_id}/\\1', decoded)
                html_parts.append(decoded)
            elif content_type == "text/plain":
                text_parts.append(decoded)
                
        if html_parts:
            return "\n<br>\n".join(html_parts)
            
        # For plain text, preserve spacing using <br> and html escape to prevent XSS
        import html
        text_content = "\n".join(t.strip() for t in text_parts if t.strip()).strip()
        return html.escape(text_content).replace('\n', '<br>\n')

    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    decoded = payload.decode(charset, errors="replace").strip()
    
    if msg.get_content_type() == "text/html":
        if gmail_id:
            decoded = re.sub(r'cid:([^\s\'"]+)', f'__API_BASE_URL__/api/emails/attachments/inline/{gmail_id}/\\1', decoded)
        return decoded
        
    import html
    return html.escape(decoded).replace('\n', '<br>\n')


def _extract_attachment_names(msg: email.message.Message) -> list[str]:
    names: list[str] = []
    for part in msg.walk():
        filename = part.get_filename()
        if filename:
            names.append(_decode_header_value(filename))
    return names


def _google_oauth_ready() -> bool:
    return bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET and GOOGLE_OAUTH_REDIRECT_URI and GOOGLE_OAUTH_ENCRYPTION_KEY)


def _build_google_flow(state: str | None = None) -> Flow:
    if not _google_oauth_ready():
        raise ValueError("Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI.")

    client_config = {
        "web": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GOOGLE_OAUTH_SCOPES, state=state)
    flow.redirect_uri = GOOGLE_OAUTH_REDIRECT_URI
    return flow


def _user_key(user_email: str) -> str:
    return hashlib.sha256(user_email.strip().lower().encode("utf-8")).hexdigest()


def _token_path_for_user(user_email: str) -> Path:
    GOOGLE_OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return GOOGLE_OAUTH_TOKENS_DIR / f"{_user_key(user_email)}.enc"


def _save_google_credentials(user_email: str, creds: Credentials) -> None:
    token_path = _token_path_for_user(user_email)
    encrypted_token = _get_google_fernet().encrypt(creds.to_json().encode("utf-8"))
    with open(token_path, "wb") as f:
        f.write(encrypted_token)


def _load_google_credentials(user_email: str) -> Credentials | None:
    token_path = _token_path_for_user(user_email)
    if not token_path.exists():
        return None

    try:
        encrypted_token = token_path.read_bytes()
        token_json = _get_google_fernet().decrypt(encrypted_token).decode("utf-8")
        token_data = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(token_data, scopes=GOOGLE_OAUTH_SCOPES)
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError):
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            _save_google_credentials(user_email, creds)
        except Exception:
            return None

    return creds if creds and creds.valid else None


def _get_gmail_api_service(user_email: str) -> Any | None:
    creds = _load_google_credentials(user_email)
    if not creds:
        return None
    try:
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _extract_email_from_credentials(creds: Credentials) -> str:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email_addr = str(profile.get("emailAddress", "")).strip().lower()
    if not email_addr:
        raise ValueError("Unable to resolve Google account email from credentials")
    return email_addr


def _session_cookie_name() -> str:
    return "aicoe_session"


def _session_token_for_user(user_email: str) -> str:
    email_norm = user_email.strip().lower()
    payload = base64.urlsafe_b64encode(email_norm.encode("utf-8")).decode("ascii")
    sig = hmac.new(APP_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _user_from_session_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, sig = token.split(".", 1)
    expected = hmac.new(APP_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        email_addr = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8").strip().lower()
    except Exception:
        return None
    return email_addr or None


def _get_authenticated_user_email(request: Request) -> str:
    # 1. CSRF Protection Check
    if request.method in ["POST", "PUT", "DELETE"]:
        if not request.headers.get("X-Requested-With"):
            raise HTTPException(status_code=403, detail="Security Header Missing (CSRF Protection)")

    # 2. Session Validation
    email_addr = _user_from_session_token(request.cookies.get(_session_cookie_name()))
    if not email_addr:
        raise HTTPException(status_code=401, detail="Not authenticated. Connect Gmail first.")
    
    # 3. Revocation Check (RISC Protection)
    from database_api import is_user_revoked
    if is_user_revoked(email_addr):
        raise HTTPException(status_code=403, detail="Account revoked due to Google Security Event. Please contact administrator.")
        
    return email_addr


def _oauth_state_cookie_name() -> str:
    return "google_oauth_state"


def _oauth_verifier_cookie_name() -> str:
    return "google_oauth_verifier"


def _is_secure_cookie_required() -> bool:
    return GOOGLE_OAUTH_COOKIE_SECURE


def _gmail_api_list_message_ids(
    service: Any, 
    limit: int = 0, 
    label_ids: list[str] = None, 
    query: str = ""
) -> list[str]:
    message_ids: list[str] = []
    page_token = None
    remaining = limit if limit > 0 else None
    
    # Priority: If label_ids are provided (e.g. ['INBOX']), use them directly.
    # This is more reliable than query strings like "in:inbox" which have index lag.
    labels = label_ids
    if not labels and not query:
        labels = ["INBOX"]

    while True:
        max_results = min(remaining, 100) if remaining is not None else 100
        req = service.users().messages().list(
            userId="me",
            labelIds=labels,
            q=query,
            pageToken=page_token,
            maxResults=max_results,
        )
        resp = req.execute()
        items = resp.get("messages", [])
        
        for item in items:
            mid = item.get("id")
            if mid and mid not in message_ids:
                message_ids.append(mid)

        if remaining is not None:
            remaining -= len(items)
            if remaining <= 0:
                break

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
            
    return message_ids


def _fetch_dynamic_gmail_messages_oauth(
    user_email: str, 
    limit: int = 0, 
    query: str = "",
    label_ids: list[str] = None
) -> tuple[list[dict[str, Any]], list[str]]:
    service = _get_gmail_api_service(user_email)
    if service is None:
        raise ValueError("Google OAuth token not available. Connect Gmail first.")

    message_ids = _gmail_api_list_message_ids(service, limit=limit, query=query, label_ids=label_ids)
    
    # NEW: Filter out IDs that already exist in our database to avoid redundant fetching
    existing_ids = get_existing_gmail_ids(user_email)
    
    new_message_ids = []
    for mid in message_ids:
        if mid not in existing_ids:
            new_message_ids.append(mid)
    
    if len(new_message_ids) < len(message_ids):
        logger.info(f"⏩ [Sync] Skipping {len(message_ids) - len(new_message_ids)} messages already in DB.")
        
    messages: list[dict[str, Any]] = []

    # Process truly new messages
    for msg_id in new_message_ids:
        try:
            payload = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
            raw_str = payload.get("raw", "")
            if not raw_str:
                continue
            msg_bytes = base64.urlsafe_b64decode(raw_str.encode("utf-8"))
            msg = email.message_from_bytes(msg_bytes)
            
            # --- EMAIL PARSING ---
            subject = _decode_header_value(msg.get("Subject")) or "(No Subject)"
            sender_full = _decode_header_value(msg.get("From"))
            sender_name, sender_email = parseaddr(sender_full)
            sender_name = sender_name.strip() or sender_email or "Unknown Sender"

            date_header = msg.get("Date")
            try:
                email_date = parsedate_to_datetime(date_header).isoformat() if date_header else datetime.now().isoformat()
            except Exception:
                email_date = datetime.now().isoformat()

            body = _extract_email_body(msg, gmail_id=msg_id)
            content = body.strip()
            message_id = str(msg.get("Message-ID", "")).strip()
            parent_message_id = str(msg.get("In-Reply-To", "")).strip()
            
            # --- ATTACHMENT PROCESSING ---
            attachment_names = []
            attachment_content_extracted = ""
            
            for part in msg.walk():
                filename = part.get_filename()
                if filename:
                    safe_name = _decode_header_value(filename)
                    payload_data = part.get_payload(decode=True)
                    if not payload_data:
                        continue
                    
                    # Generate unique filename
                    from hashlib import md5
                    file_hash = md5(payload_data).hexdigest()[:8]
                    unique_name = f"{file_hash}_{safe_name.replace(' ', '_')}"
                    attachment_path = os.path.join(ATTACHMENTS_DIR, unique_name)
                    
                    # Save locally
                    try:
                        with open(attachment_path, "wb") as f:
                            f.write(payload_data)
                        attachment_names.append(unique_name)
                        
                        # OCR / Extraction
                        attachment_content_extracted += extract_attachment_text(attachment_path)
                    except Exception as e:
                        logger.error(f"⚠️ Failed to process attachment {safe_name}: {e}")

            # Collect into the common format
            messages.append({
                "email_id": _generate_email_id(message_id or content),
                "parent_email_id": _generate_email_id(parent_message_id) if parent_message_id else "",
                "thread_id": str(payload.get("threadId", "")).strip(),
                "sender": sender_name,
                "sender_email": sender_email or "",
                "subject": subject,
                "date": email_date,
                "content": content,
                "attachments": attachment_names,
                "attachment_content": attachment_content_extracted,
                "raw_message_id": message_id,
                "gmail_id": msg_id,
            })
            
        except Exception as e:
            logger.error(f"Error fetching message {msg_id}: {e}")
            continue

    return messages, message_ids


def _get_user_display_name(user_email: str) -> str:
    """Fetch user's Send-As name from Gmail Settings, with caching and fallback to profile/email prefix."""
    if user_email in _user_display_name_cache:
        return _user_display_name_cache[user_email]

    logger.info(f"🔍 Fetching display name for {user_email}...")
    try:
        service = _get_gmail_api_service(user_email)
        if service:
            # 1. Try Gmail Settings (Send As) - This is the primary source for Gmail "Alias" name
            try:
                send_as = service.users().settings().sendAs().list(userId='me').execute()
                primary = next((s for s in send_as.get('sendAs', []) if s.get('isPrimary')), None)
                if primary and primary.get('displayName'):
                    logger.info(f"✅ Found Gmail Send-As name: {primary['displayName']}")
                    _user_display_name_cache[user_email] = primary['displayName']
                    return primary['displayName']
            except Exception as se:
                logger.warning(f"Gmail Settings name fetch failed: {se}")
            
            # 2. Try People API (as fallback)
            try:
                people_service = build('people', 'v1', credentials=_get_google_credentials(user_email))
                profile = people_service.people().get(resourceName='people/me', personFields='names').execute()
                if 'names' in profile and profile['names']:
                    name = profile['names'][0].get('displayName')
                    if name:
                        logger.info(f"✅ Found People API profile name: {name}")
                        _user_display_name_cache[user_email] = name
                        return name
            except Exception as pe:
                logger.warning(f"People API fallback failed: {pe}")
    except Exception as e:
        logger.error(f"Failed to fetch user display name from APIs: {e}")

    # 3. Ultimate Fallback: Email Prefix
    fallback_name = user_email.split('@')[0].capitalize()
    logger.info(f"⚠️ Falling back to email prefix name: {fallback_name}")
    _user_display_name_cache[user_email] = fallback_name
    return fallback_name


def _get_google_credentials(user_email: str) -> Optional[Credentials]:
    """Helper to get Credentials object for building other services."""
    token_path = GOOGLE_OAUTH_TOKENS_DIR / f"{hashlib.sha256(user_email.encode()).hexdigest()}.enc"
    if not token_path.exists():
        return None
    try:
        fernet = _get_google_fernet()
        with open(token_path, "rb") as f:
            enc_data = f.read()
        creds_json = fernet.decrypt(enc_data).decode("utf-8")
        return Credentials.from_authorized_user_info(json.loads(creds_json))
    except Exception:
        return None


def _send_email_via_gmail_api(user_email: str, to_email: str, subject: str, body: str, thread_id: str = None, in_reply_to: str = None) -> str | None:
    service = _get_gmail_api_service(user_email)
    if service is None:
        return None

    display_name = _get_user_display_name(user_email)
    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = f"{display_name} <{user_email}>"
    msg["Subject"] = subject
    
    # Threading Headers
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
        
    msg.set_content(body)
    raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        body_payload = {"raw": raw_msg}
        if thread_id:
            body_payload["threadId"] = thread_id
            
        sent_msg = service.users().messages().send(userId="me", body=body_payload).execute()
        return sent_msg.get("id")
    except HttpError as e:
        logger.error(f"Gmail Send Error: {e}")
        return None


def _fetch_dynamic_gmail_messages(user_email: str, limit: int = 0) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    """Fetch messages from both INBOX and SENT to track full conversation state."""
    service = _get_gmail_api_service(user_email)
    if service is None:
        raise ValueError("Gmail OAuth token not available or invalid. Reconnect Gmail through the app.")
    
    # 1. Fetch from Primary Inbox Only (Zero-Lag direct label access)
    inbox_ids_raw = _gmail_api_list_message_ids(service, limit=limit, label_ids=["INBOX"])
    inbox_messages, _ = _fetch_dynamic_gmail_messages_oauth(user_email, limit=limit, label_ids=["INBOX"])
    for msg in inbox_messages:
        msg["is_inbox"] = True
    inbox_ids_set = set(inbox_ids_raw)
    
    # 2. Fetch from Sent
    sent_limit = limit if limit > 0 else 100
    sent_ids_raw = _gmail_api_list_message_ids(service, limit=sent_limit, label_ids=["SENT"])
    sent_messages, _ = _fetch_dynamic_gmail_messages_oauth(user_email, limit=sent_limit, label_ids=["SENT"])
    for msg in sent_messages:
        msg["is_sent"] = True
        msg["is_sent_by_me"] = True

    # 3. Fetch from Trash
    trash_limit = limit if limit > 0 else 100
    trash_ids_raw = _gmail_api_list_message_ids(service, limit=trash_limit, label_ids=["TRASH"])
    trash_messages, _ = _fetch_dynamic_gmail_messages_oauth(user_email, limit=trash_limit, label_ids=["TRASH"])
    for msg in trash_messages:
        msg["category"] = "trash"
        msg["is_trashed"] = True

    return inbox_messages + sent_messages + trash_messages, {
        "inbox_ids": inbox_ids_set,
        "sent_ids": set(sent_ids_raw),
        "trash_ids": set(trash_ids_raw)
    }


def _build_dynamic_dataframe(user_email: str) -> pd.DataFrame:
    try:
        new_messages, folder_ids = _fetch_dynamic_gmail_messages(user_email)
    except Exception as e:
        new_messages = []
        folder_ids = {}
    
    # 1.5. RECONCILE FLAGS (Fix Ghost Emails)
    # If this is a full sync (which it is here because limit=0), we reconcile the flags.
    from database_api import reconcile_email_flags, purge_orphaned_emails
    if folder_ids:
        reconcile_email_flags(user_email, 'inbox', folder_ids.get("inbox_ids", set()))
        reconcile_email_flags(user_email, 'sent', folder_ids.get("sent_ids", set()))
        reconcile_email_flags(user_email, 'trash', folder_ids.get("trash_ids", set()))
        
        # 1.6. LEAN SYNC PURGE
        # Permanently delete emails that have been 'orphaned' (not in any folder) for 30+ days.
        purge_orphaned_emails(user_email)
    
    # 2. Load existing emails from DB to provide context for followup detection
    from database_api import get_emails_from_db
    # We fetch everything currently in DB to ensure we don't lose anything
    existing_emails = get_emails_from_db(user_email, category='all')
    existing_df = pd.DataFrame(existing_emails)

    if not new_messages:
        print("ℹ️ [Sync] No new messages to process.")
        return existing_df

    # 3. Process new messages
    new_rows = []
    # [THREAD CONTEXT FIX]: Maintain a dynamic context of emails processed in THIS batch 
    # to link them correctly even if they aren't in the database yet.
    current_context_df = existing_df.copy()

    for msg in new_messages:

        category = classify_grievance(
            msg["content"],
            subject=msg.get("subject", ""),
            attachment_content=msg.get("attachment_content", "")
        )
        mail_type, parent_id, followup_count = detect_followup(msg, current_context_df)

        # Always score immediately with deterministic heuristic in request path.
        # Optional LLM refinement is applied asynchronously in background.
        base_priority = _heuristic_priority(msg.get("content", ""), msg.get("subject", ""))

        final_priority = apply_thread_escalation(base_priority, followup_count)
        if final_priority is None:
            final_priority = base_priority

        institute_guess = msg.get("sender_email", "").split("@")[-1] if msg.get("sender_email") else "Unknown Institute"

        final_category = msg.get("category") or category
        if final_category == "Miscellaneous" and msg.get("is_sent_by_me"):
            final_category = "Sent"

        # Only mark as 'replied' if it's a genuine response to a different sender, 
        # not just because it's a self-sent test grievance.
        sender_email = msg.get("sender_email", "").strip().lower()
        user_email_norm = user_email.strip().lower()
        is_self_sent = sender_email == user_email_norm
        
        # A reply is specifically an email I sent to SOMEONE ELSE.
        # If I sent it to myself (a self-sent test grievance), it's not a reply, it's a grievance.
        is_inbox = msg.get("is_inbox", False)
        is_sent_by_me = msg.get("is_sent_by_me", False)
        is_replied = is_sent_by_me and not is_self_sent

        row = {
            "email_id": msg["email_id"],
            "parent_email_id": parent_id or msg.get("parent_email_id", ""),
            "thread_id": msg.get("thread_id", ""),
            "sender": msg.get("sender", "Unknown Sender"),
            "sender_email": sender_email,
            "institute_name": institute_guess,
            "subject": msg.get("subject", ""),
            "category": final_category,
            "mail_type": mail_type,
            "followup_count": followup_count,
            "priority": int(final_priority),
            "date": msg.get("date", datetime.now().date().isoformat()),
            "content": msg.get("content", ""),
            "attachments": msg.get("attachments", []),
            "attachment_content": msg.get("attachment_content", ""),
            "eml_file": msg.get("raw_message_id", ""),
            "gmail_id": msg.get("gmail_id", ""),
            "is_demo": False,
            "replied": is_replied,
            "is_inbox": is_inbox,
            "is_sent": msg.get("is_sent", False),
            "is_trashed": 1 if msg.get("category") == "trash" else 0,
        }

        new_rows.append(row)
        # Add to local context so subsequent emails in same thread can see it
        current_context_df = pd.concat([current_context_df, pd.DataFrame([row])], ignore_index=True)

    # 6. Final Merge
    if not new_messages:
        return existing_df
        
    new_df = pd.DataFrame(new_rows)
    final_df = pd.concat([existing_df, new_df], ignore_index=True)
    
    # [NAN FIX]: Sanitize numeric columns to prevent "float NaN to integer" crashes
    numeric_defaults = {
        "priority": 6,
        "followup_count": 0,
        "replied": 0,
        "is_trashed": 0,
        "is_inbox": 0,
        "is_sent": 0,
        "is_priority_refined": 0
    }
    for col, default in numeric_defaults.items():
        if col in final_df.columns:
            final_df[col] = final_df[col].fillna(default)
            
    return final_df


def _persist_dynamic_cache(user_email: str, df: pd.DataFrame, *, cached_at: datetime | None = None) -> None:
    key = _user_key(user_email)
    stamp = cached_at or datetime.now()
    lock = _get_user_lock(user_email)
    with lock:
        _dynamic_cache_df_by_user[key] = df.copy()
        _dynamic_cache_at_by_user[key] = stamp

    # Save to SQLite DB for persistence and instant updates
    try:
        emails_list = df.to_dict(orient="records")
        save_emails_batch(user_email, emails_list)
    except Exception as e:
        print(f"⚠️ Failed to persist to SQLite: {e}")


def _run_priority_llm_enrichment(user_email: str) -> None:
    # 1. Brief pause to let initial sync/UI render settle
    time.sleep(5)
    
    key = _user_key(user_email)
    snapshot_df: pd.DataFrame | None = None
    
    # [CRASH FIX]: Initialize variables to prevent UnboundLocalError in finally block
    updates = {}
    newly_scored = set()

    try:
        lock = _get_user_lock(user_email)
        with lock:
            cached_df = _dynamic_cache_df_by_user.get(key)
            if cached_df is not None:
                snapshot_df = cached_df.copy()

        if snapshot_df is None or snapshot_df.empty:
            return

        # 2. POPULATE SCORED_IDS FROM DATABASE [REINFORCEMENT]
        # This ensures that even after a restart, we don't re-score anything
        scored_ids = _priority_llm_scored_ids_by_user.get(key, set())
        
        try:
            from database_api import DB_PATH
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM emails WHERE user_email = ? AND is_priority_refined = 1", (user_email,))
            db_refined_ids = {str(row[0]).strip().lower() for row in cursor.fetchall()}
            # [CACHE LEAK FIX]: Directly equate scored_ids to the database truth. This solves the bug 
            # where wiping the database would leave 70 stale IDs in RAM causing the stats screen to report
            # 70/70 completion when none had actually been re-scored yet.
            scored_ids = db_refined_ids
            _priority_llm_scored_ids_by_user[key] = scored_ids
            conn.close()
        except Exception as db_err:
            print(f"⚠️ Warning: Could not pre-fetch refined IDs from DB: {db_err}")
        
        # 2. Collect only unscored emails
        to_score = []
        for _, row in snapshot_df.iterrows():
            email_id = str(row.get("email_id", "")).strip().lower()
            # [STRICT SKIP]: Use the persistent is_priority_refined flag from DB
            is_already_refined = row.get("is_priority_refined", 0)
            if not email_id or is_already_refined == 1:
                continue
            
            # Legacy/Safety check for in-memory set (during a long running session)
            if email_id in scored_ids:
                continue
            
            # Defense against NaN for numeric calculation
            f_count = row.get("followup_count", 0)
            if pd.isna(f_count):
                f_count = 0
            
            to_score.append({
                "id": email_id,
                "sender": row.get("sender", "Unknown"),
                "subject": row.get("subject", "No Subject"),
                "content": row.get("content", ""),
                "followup_count": int(f_count)
            })

        if not to_score:
            return

        # 3. Process a larger batch to maximize the Gemini Free Tier's daily request limit (e.g., 20 requests per day)
        batch_size = 15
        batch = to_score[:batch_size]
        
        print(f"Refining priority for a batch of {len(batch)} emails...")
        
        # This call is rate-limited inside priority_llm.py (max 5 per 5 mins)
        batch_results = get_batch_priorities(batch)
        print(f"DEBUG: LLM returned {len(batch_results)} results for batch of {len(batch)}.")
        if batch_results:
            print(f"DEBUG: Returned IDs: {list(batch_results.keys())}")
            print(f"DEBUG: Expected IDs: {[e['id'].lower() for e in batch]}")
        
        if not batch_results:
            print(f"Priority batch refinement returned no results (rate limit or failure).")
            return
            
        for email in batch:
            eid = email["id"].lower()
            if eid in batch_results:
                llm_p = batch_results[eid]
                final_p = apply_thread_escalation(llm_p, email["followup_count"])
                updates[eid] = int(final_p)
                newly_scored.add(eid)
                
        if not updates:
            return

        # 4. Save results of this batch immediately to the live cache
        persist_df: pd.DataFrame | None = None
        lock = _get_user_lock(user_email)
        with lock:
            live_df = _dynamic_cache_df_by_user.get(key)
            if live_df is not None:
                live_df = live_df.copy()
                for eid, priority in updates.items():
                    mask = live_df["email_id"].astype(str).str.lower() == eid.lower()
                    if mask.any():
                        live_df.loc[mask, "priority"] = int(priority)
                        live_df.loc[mask, "is_priority_refined"] = 1 # Mark as refined permanently
                
                _dynamic_cache_df_by_user[key] = live_df
                _dynamic_cache_at_by_user[key] = datetime.now()
                
                # --- THREAD SAFE SET UPDATE ---
                scored_store = _priority_llm_scored_ids_by_user.get(key)
                if scored_store is None:
                    scored_store = set()
                    _priority_llm_scored_ids_by_user[key] = scored_store
                scored_store.update(newly_scored)
                persist_df = live_df

        if persist_df is not None:
            # 1. Update Excel
            os.makedirs(os.path.dirname(EXCEL_FILE), exist_ok=True)
            persist_df.to_excel(EXCEL_FILE, index=False)
            
            # 2. Update SQLite Persistence [NEW FIX]
            batch_records = persist_df.to_dict(orient="records")
            save_emails_batch(user_email, batch_records)
            
            print(f"✓ AI Priority Refinement saved to DB (ID count: {len(newly_scored)}).")

    except Exception as exc:
        print(f"Priority enrichment thread error: {exc}")
    finally:
        # 5. Handle success/failure status for backoff
        lock = _get_user_lock(user_email)
        with lock:
            _priority_llm_worker_running_by_user[key] = False
            if updates:
                # Any successful update resets the failure count
                _priority_llm_consecutive_failures_by_user[key] = 0
            else:
                # If the whole run failed (or break due to rate limit), increment failures
                current_fail = _priority_llm_consecutive_failures_by_user.get(key, 0)
                _priority_llm_consecutive_failures_by_user[key] = current_fail + 1


def _schedule_priority_llm_enrichment(user_email: str) -> None:
    if not DYNAMIC_USE_LLM_PRIORITY:
        return

    key = _user_key(user_email)
    now = datetime.now()

    # 1. Check if a worker is already active
    lock = _get_user_lock(user_email)
    with lock:
        if _priority_llm_worker_running_by_user.get(key, False):
            return
            
        # 2. Check cooldown since last START
        last_run = _priority_llm_last_run_by_user.get(key)
        fail_count = _priority_llm_consecutive_failures_by_user.get(key, 0)
        
        # INCREASED COOLDOWN: 60 seconds base
        # BACKOFF: If it failed multiple times, wait longer (e.g. 5 mins after 3 fails)
        cooldown = 60
        if fail_count >= 3:
            cooldown = 300 # 5 minute backoff
            
        if last_run and (now - last_run).total_seconds() < cooldown:
            return

        # 3. Smart Skip: Check if there's actually anything to score before starting
        cached_df = _dynamic_cache_df_by_user.get(key)
        if cached_df is None or cached_df.empty:
            return
            
        has_unscored = False
        for _, row in cached_df.iterrows():
            eid = str(row.get("email_id", "")).strip()
            is_ref = row.get("is_priority_refined", 0)
            
            # If any email is not refined yet, we have work to do
            if eid and is_ref == 0:
                has_unscored = True
                break
                
        if not has_unscored:
            # All caught up! No need to wake the AI.
            return

        # Start the worker
        _priority_llm_worker_running_by_user[key] = True
        _priority_llm_last_run_by_user[key] = now

    worker = threading.Thread(
        target=_run_priority_llm_enrichment,
        args=(user_email,),
        daemon=True,
        name=f"priority-llm-{key[:8]}",
    )
    worker.start()


def _send_demo_emails_to_gmail_inbox(user_email: str) -> Dict[str, Any]:
    demo_emails = _load_demo_emails()
    sent = 0

    service = _get_gmail_api_service(user_email)
    if service is None:
        raise ValueError("Google OAuth token not available. Connect Gmail through the app first.")

    for item in demo_emails:
        subject = str(item.get("subject", "")).strip() or "Demo grievance"
        if not subject.startswith(SEEDED_SUBJECT_PREFIX):
            subject = f"{SEEDED_SUBJECT_PREFIX} {subject}"
        body = str(item.get("body", "")).strip() or "This is a demo grievance email."
        if _send_email_via_gmail_api(user_email, user_email, subject, body):
            sent += 1

    return {
        "sent_count": sent,
        "target_mailbox": user_email,
    }


def _send_excel_emails_to_gmail_inbox(user_email: str, *, only_demo: bool = True, limit: int = 0) -> Dict[str, Any]:
    if not os.path.exists(EXCEL_FILE):
        raise FileNotFoundError(f"Excel source not found: {EXCEL_FILE}")

    df = pd.read_excel(EXCEL_FILE)
    if df.empty:
        return {
            "sent_count": 0,
            "source_rows": 0,
            "target_mailbox": user_email,
            "only_demo": only_demo,
            "limit": limit,
        }

    if only_demo and "is_demo" in df.columns:
        df = df[df["is_demo"].astype(str).str.lower().isin(["true", "1"])]

    if limit and limit > 0:
        df = df.head(limit)

    service = _get_gmail_api_service(user_email)
    if service is None:
        raise ValueError("Google OAuth token not available. Connect Gmail through the app first.")

    sent = 0
    for _, row in df.iterrows():
        subject = str(row.get("subject", "")).strip() or "Grievance Email"
        if not subject.startswith(SEEDED_SUBJECT_PREFIX):
            subject = f"{SEEDED_SUBJECT_PREFIX} {subject}"
        content = str(row.get("content", "")).strip()
        sender = str(row.get("sender", "")).strip()
        sender_email = str(row.get("sender_email", "")).strip()

        body_prefix = []
        if sender:
            body_prefix.append(f"Sender: {sender}")
        if sender_email and sender_email.lower() != "nan":
            body_prefix.append(f"Sender Email: {sender_email}")

        full_body = "\n".join(body_prefix + ["", content if content and content.lower() != "nan" else "No content provided."]).strip()
        if _send_email_via_gmail_api(user_email, user_email, subject, full_body):
            sent += 1

    return {
        "sent_count": sent,
        "source_rows": int(len(df)),
        "target_mailbox": user_email,
        "only_demo": only_demo,
        "limit": limit,
    }


def _cleanup_seeded_emails_in_gmail(user_email: str, *, dry_run: bool = True, limit: int = 0, only_inbox: bool = True) -> Dict[str, Any]:
    service = _get_gmail_api_service(user_email)
    if service is None:
        raise ValueError("Google OAuth token not available. Connect Gmail through the app first.")

    query = f'subject:"{SEEDED_SUBJECT_PREFIX}"'
    label_ids = ["INBOX"] if only_inbox else None
    message_ids = _gmail_api_list_message_ids(service, limit=limit, query=query, label_ids=label_ids)

    trashed = 0
    if not dry_run:
        for msg_id in message_ids:
            try:
                service.users().messages().trash(userId="me", id=msg_id).execute()
                trashed += 1
            except Exception:
                continue

    return {
        "matched_count": len(message_ids),
        "trashed_count": trashed,
        "dry_run": dry_run,
        "only_inbox": only_inbox,
        "limit": limit,
        "subject_prefix": SEEDED_SUBJECT_PREFIX,
    }


def _refresh_dynamic_cache(user_email: str, force_refresh: bool = False) -> pd.DataFrame:
    key = _user_key(user_email)
    lock = _get_user_lock(user_email)
    
    # 1. Check if another sync is already in progress for this user
    if _is_syncing_by_user.get(user_email, False):
        logger.info(f"⏳ [Sync] Sync already in progress for {user_email}. Skipping overlapping request.")
        with lock:
            return _dynamic_cache_df_by_user.get(key, pd.DataFrame(columns=COLUMNS)).copy()

    with lock:
        cached_df = _dynamic_cache_df_by_user.get(key)
        cached_at = _dynamic_cache_at_by_user.get(key)
        
        now = datetime.now()
        cache_valid = (
            cached_df is not None
            and cached_at is not None
            and DYNAMIC_AUTO_REFRESH_SECONDS > 0
            and (now - cached_at).total_seconds() < DYNAMIC_AUTO_REFRESH_SECONDS
        )

        if not force_refresh and cache_valid:
            _schedule_priority_llm_enrichment(user_email)
            return cached_df.copy()

    # 2. Perform the actual refresh with robust state protection
    _is_syncing_by_user[user_email] = True
    try:
        logger.info(f"🔄 [Sync] Starting high-parity Gmail sync for {user_email}...")
        df = _build_dynamic_dataframe(user_email)
        _persist_dynamic_cache(user_email, df, cached_at=datetime.now())
        _schedule_priority_llm_enrichment(user_email)
        return df
    finally:
        _is_syncing_by_user[user_email] = False
        logger.info(f"✅ [Sync] Sync finished for {user_email}.")


def _get_active_dataframe(user_email: str, force_refresh: bool = False) -> pd.DataFrame:
    try:
        return _refresh_dynamic_cache(user_email, force_refresh=force_refresh)
    except Exception as exc:
        print(f"[WARN] Dynamic refresh failed, falling back to Excel cache: {exc}")
        if os.path.exists(EXCEL_FILE):
            return pd.read_excel(EXCEL_FILE)
        return pd.DataFrame(columns=COLUMNS)


def _collect_policy_pdf_files(*directories: Path) -> list[Path]:
    pdf_candidates: list[Path] = []
    for directory in directories:
        pdf_candidates.extend(list(directory.glob("*.pdf")) + list(directory.glob("*.PDF")))
    return sorted({p.resolve() for p in pdf_candidates})


def _sync_policy_pdfs_from_disk(*, include_demo: bool = True, include_uploaded: bool = True) -> Dict[str, Any]:
    """Rebuild the policy corpus from PDFs stored on disk."""
    directories: list[Path] = []
    if include_uploaded:
        directories.append(POLICY_DIR)
    if include_demo:
        directories.append(DEMO_POLICY_DIR)

    pdf_files = _collect_policy_pdf_files(*directories)

    if not pdf_files:
        return {
            "pdf_count": 0,
            "indexed_count": 0,
            "chunks_path": str(CHUNKS_PATH),
            "index_path": str(INDEX_PATH),
        }

    # ONLY delete if we are forcing a rebuild or if the files are missing.
    # Otherwise, we keep existing index to make startup instant.
    if include_demo and not (CHUNKS_PATH.exists() and INDEX_PATH.exists()):
        print("[INFO] Policy index or chunks missing. Rebuilding from scratch...")
        if CHUNKS_PATH.exists():
            CHUNKS_PATH.unlink()
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
    elif not include_demo:
        # If we're doing a manual sync (usually via POST /policies/load-demo), we rebuild.
        print("[INFO] Manual policy sync requested. Rebuilding index...")
        if CHUNKS_PATH.exists():
            CHUNKS_PATH.unlink()
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
    else:
        print("[INFO] Current policy index found. Skipping redundant rebuild at startup.")
        return {
            "pdf_count": len(pdf_files),
            "indexed_count": len(pdf_files),
            "status": "up-to-date"
        }

    generated_any = False
    for pdf_path in pdf_files:
        try:
            section_title = "Demo Policy" if pdf_path.parent == DEMO_POLICY_DIR else "General"
            ingest_policy_document(
                file_path=str(pdf_path),
                policy_id=pdf_path.stem,
                section_title=section_title,
            )
            generated_any = True
        except Exception as exc:
            print(f"[WARN] Failed to ingest policy PDF {pdf_path.name}: {exc}")

    if not generated_any:
        return {
            "pdf_count": len(pdf_files),
            "indexed_count": 0,
            "chunks_path": str(CHUNKS_PATH),
            "index_path": str(INDEX_PATH),
        }

    reload_retriever_data(force=True)
    return {
        "pdf_count": len(pdf_files),
        "indexed_count": len(pdf_files),
        "chunks_path": str(CHUNKS_PATH),
        "index_path": str(INDEX_PATH),
    }


def _sync_demo_policy_pdfs(force_index_rebuild: bool = False) -> Dict[str, Any]:
    """Build the demo policy corpus from PDFs placed in backend/demo_policies."""
    return _sync_policy_pdfs_from_disk(include_demo=True, include_uploaded=False)

def run(user_email: str, source_mode_override: str | None = None):
    # Ensure the active corpus reflects PDFs on disk before processing emails.
    _sync_policy_pdfs_from_disk(include_demo=True, include_uploaded=True)

    print(f"🔌 Email source mode: dynamic (Gmail inbox: {user_email})")
    df = _refresh_dynamic_cache(user_email, force=True)

    # Clean all text fields for Excel compatibility
    print("\n🧹 Cleaning data for Excel compatibility...")
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].apply(clean_for_excel)
    
    df.to_excel(EXCEL_FILE, index=False)
    print(f"\n✅ Processing complete! Total records: {len(df)}")
    print(f"📊 Data saved to: {EXCEL_FILE}")

# --- BACKGROUND SYNC WORKER ---
_background_sync_running_by_user: Dict[str, bool] = {}
_user_sync_intervals: Dict[str, int] = {} # user_email -> seconds

def _run_background_sync_loop(user_email: str):
    """Background loop that refreshes the Gmail cache every N seconds."""
    if _background_sync_running_by_user.get(user_email):
        logger.info(f"🔁 [Sync] Worker already running for {user_email}.")
        return

    _background_sync_running_by_user[user_email] = True
    logger.info(f"🚀 [Sync] Automatic Background Worker started for {user_email}.")
    
    while _background_sync_running_by_user.get(user_email):
        try:
            # Refresh both message IDs and classifications
            _refresh_dynamic_cache(user_email, force_refresh=True)
            logger.info(f"✅ [Sync] Automatic periodic refresh complete for {user_email}.")
        except Exception as e:
            logger.error(f"❌ [Sync] Periodic background sync failed: {e}")
        
        # Determine how long to sleep (respect dynamic settings)
        interval = _user_sync_intervals.get(user_email, DYNAMIC_AUTO_REFRESH_SECONDS)
        time.sleep(max(5, interval)) # Min 5s safety

# ---------------- FASTAPI APP ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler for startup and shutdown procedures.
    """
    # 1. Background startup (Warmup & Search Index check)
    def _background_startup_tasks():
        synced = _sync_policy_pdfs_from_disk(include_demo=True, include_uploaded=True)
        if synced.get("pdf_count"):
            print(f"[INFO] Policy corpus checked. Status: {synced.get('status', 'synced')}")
        
        get_embedder()
        print("✅ Background model warmup complete.")

    threading.Thread(target=_background_startup_tasks, daemon=True).start()
    
    # 2. AUTO-SYNC: Check if we have a default/seeded user to start syncing for
    # In a full multi-user app, this would start on first user login.
    # Here we check for the GMAIL_ADDRESS in .env as the primary user.
    if GMAIL_ADDRESS and "your-project@gmail.com" not in GMAIL_ADDRESS:
        threading.Thread(
            target=_run_background_sync_loop, 
            args=(GMAIL_ADDRESS,), 
            daemon=True,
            name=f"sync-{GMAIL_ADDRESS[:8]}"
        ).start()

    yield
    # SHUTDOWN
    print("Gracefully shutting down...")
    for key in _background_sync_running_by_user:
        _background_sync_running_by_user[key] = False

# ---------------- FASTAPI APP ----------------
app = FastAPI(
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for frontend
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003,http://localhost:3004,http://localhost:3005,http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_validate_runtime_configuration()

# ---------------- FASTAPI APP ----------------

@app.get("/")
def root():
    return {"status": "Backend running on Hugging Face"}

@app.get("/health")
def health_check():
    """Health check endpoint for Docker/load balancer"""
    return {"status": "healthy", "service": "AI Grievance Management Backend"}


class GoogleAuthStatusResponse(BaseModel):
    connected: bool
    email: str | None = None
    auth_mode: str = "none"


def _get_connected_gmail_identity(user_email: str) -> str | None:
    service = _get_gmail_api_service(user_email)
    if service is None:
        return None
    try:
        profile = service.users().getProfile(userId="me").execute()
        return str(profile.get("emailAddress", "")).strip() or None
    except Exception:
        return None


@app.get("/auth/google/start")
def start_google_auth():
    if not _google_oauth_ready():
        raise HTTPException(
            status_code=500,
            detail="Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI, and GOOGLE_OAUTH_ENCRYPTION_KEY.",
        )

    flow = _build_google_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    code_verifier = getattr(flow, "code_verifier", None)
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key=_oauth_state_cookie_name(),
        value=state,
        max_age=300,
        httponly=True,
        secure=_is_secure_cookie_required(),
        samesite="lax",
        path="/",
    )
    if code_verifier:
        response.set_cookie(
            key=_oauth_verifier_cookie_name(),
            value=code_verifier,
            max_age=300,
            httponly=True,
            secure=_is_secure_cookie_required(),
            samesite="lax",
            path="/",
        )
    return response


@app.get("/auth/google/callback")
def complete_google_auth(request: Request, code: str | None = None, state: str | None = None):
    cookie_state = request.cookies.get(_oauth_state_cookie_name())
    code_verifier = request.cookies.get(_oauth_verifier_cookie_name())

    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")
    if not state or not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth code verifier. Restart Google sign-in from the app.")

    try:
        flow = _build_google_flow(state=state)
        flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        user_email = _extract_email_from_credentials(flow.credentials)
        _save_google_credentials(user_email, flow.credentials)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google OAuth token exchange failed: {exc}")

    if GOOGLE_OAUTH_SUCCESS_REDIRECT_URL:
        response = RedirectResponse(url=GOOGLE_OAUTH_SUCCESS_REDIRECT_URL)
        response.delete_cookie(_oauth_state_cookie_name(), path="/")
        response.delete_cookie(_oauth_verifier_cookie_name(), path="/")
        response.set_cookie(
            key=_session_cookie_name(),
            value=_session_token_for_user(user_email),
            max_age=86400,
            httponly=True,
            secure=_is_secure_cookie_required(),
            samesite="lax",
            path="/",
        )
        return response

    response = HTMLResponse(content="<html><body style='font-family:Arial,sans-serif;padding:24px;'><h2>Gmail Connected</h2><p>You can close this tab and return to the application.</p></body></html>")
    response.delete_cookie(_oauth_state_cookie_name(), path="/")
    response.delete_cookie(_oauth_verifier_cookie_name(), path="/")
    response.set_cookie(
        key=_session_cookie_name(),
        value=_session_token_for_user(user_email),
        max_age=86400,
        httponly=True,
        secure=_is_secure_cookie_required(),
        samesite="lax",
        path="/",
    )
    return response


@app.get("/auth/google/status", response_model=GoogleAuthStatusResponse)
def google_auth_status(request: Request):
    session_email = _user_from_session_token(request.cookies.get(_session_cookie_name()))
    if not session_email:
        return GoogleAuthStatusResponse(connected=False, email=None, auth_mode="none")

    connected_email = _get_connected_gmail_identity(session_email)
    if connected_email:
        return GoogleAuthStatusResponse(connected=True, email=connected_email, auth_mode="oauth")

    return GoogleAuthStatusResponse(connected=False, email=None, auth_mode="none")


@app.post("/auth/google/logout")
def google_auth_logout(request: Request):
    session_email = _user_from_session_token(request.cookies.get(_session_cookie_name()))
    if session_email:
        token_path = _token_path_for_user(session_email)
        if token_path.exists():
            token_path.unlink()
    response = JSONResponse({"success": True, "message": "Google OAuth disconnected"})
    response.delete_cookie(_session_cookie_name(), path="/")
    return response
    
@app.get("/categories")
def get_categories(request: Request, background_tasks: BackgroundTasks):
    """Get all categories with count"""
    user_email = _get_authenticated_user_email(request)
    df = _get_active_dataframe(user_email)
    if df.empty:
        # If DB is empty, trigger a sync in the background
        background_tasks.add_task(_refresh_dynamic_cache, user_email)
        return []

    categories = df.groupby("category").size().reset_index(name="count")
    
    return [
        {"name": row["category"], "count": int(row["count"])}
        for _, row in categories.iterrows()
    ]


@app.get("/colleges")
def get_colleges():
    """Get list of all colleges in database"""
    return {"colleges": COLLEGES_DB, "total": len(COLLEGES_DB)}


@app.get("/emails")
def get_emails(
    request: Request,
    background_tasks: BackgroundTasks,
    category: str = Query(..., description="Email category or 'all' for all categories"),
    is_demo: str = Query(None, description="Filter by is_demo: 'true', 'false', or None for all")
):
    """Get all emails from persistent SQLite store, with optional category/demo filtering"""
    try:
        user_email = _get_authenticated_user_email(request)
        
        demo_bool = None
        if is_demo:
            demo_bool = is_demo.lower() == "true"
            
        emails = get_emails_from_db(user_email, category, demo_bool)
        
        # If the DB is empty (first login), warm it up in the background
        if not emails:
            print(f"DB empty for category '{category}', triggering background sync...")
            background_tasks.add_task(_refresh_dynamic_cache, user_email)
        
        print(f"Found {len(emails)} emails in DB for category '{category}'")
        return emails
    except Exception as e:
        print(f"Error in get_emails: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/emails/threads/{thread_id}")
def get_email_thread(thread_id: str, request: Request):
    """Get all emails belonging to a specific thread, sorted by date."""
    try:
        user_email = _get_authenticated_user_email(request)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetch all messages in the thread
        try:
            # Try date-based sort
            cursor.execute("""
                SELECT * FROM emails 
                WHERE thread_id = ? AND user_email = ?
                ORDER BY date ASC
            """, (thread_id, user_email))
        except sqlite3.OperationalError as se:
            logger.error(f"SQL Error in get_email_thread: {se}")
            # Fallback for older DB schemas
            cursor.execute("""
                SELECT * FROM emails 
                WHERE thread_id = ?
                ORDER BY id ASC
            """, (thread_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convert rows to list of dicts
        results = []
        for row in rows:
            d = dict(row)
            # Re-format attachments if stored as JSON string
            if d.get("attachments") and isinstance(d["attachments"], str):
                try:
                    d["attachments"] = json.loads(d["attachments"])
                except:
                    pass
            results.append(d)
            
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch thread: {e}")

@app.get("/refinement-stats")
def get_refinement_stats_endpoint(request: Request):
    """Get count of AI refined vs total emails"""
    try:
        user_email = _get_authenticated_user_email(request)
        from database_api import get_refinement_stats
        return get_refinement_stats(user_email)
    except Exception as e:
        print(f"Error fetching refinement stats: {e}")
        return {"refined": 0, "total": 0}

@app.get("/sync-status")
def get_sync_status(request: Request):
    """Check if the background sync worker is currently active."""
    user_email = _get_authenticated_user_email(request)
    return {"syncing": _is_syncing_by_user.get(user_email, False)}

@app.post("/emails/{email_id}/attachments/reprocess")
def reprocess_attachment(request: Request, email_id: str, filename: str = Query(...)):
    """Force an AI OCR re-scan of a specific attachment for an email."""
    try:
        user_email = _get_authenticated_user_email(request)
        file_path = os.path.join(ATTACHMENTS_DIR, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Attachment file not found locally.")
            
        logger.info(f"🔍 [OCR] Manually re-processing {filename} for email {email_id}...")
        extracted_text = extract_text_from_attachment_ai(file_path)
        
        if extracted_text:
            update_email_attachment_content(user_email, email_id, extracted_text)
            # Clear cache so the frontend sees the new content immediately
            key = _user_key(user_email)
            with _get_user_lock(user_email):
                _dynamic_cache_df_by_user.pop(key, None)
            return {"status": "success", "extracted_text": extracted_text}
        else:
            return {"status": "failed", "detail": "AI OCR returned no text."}
            
    except Exception as e:
        logger.error(f"Error reprocessing attachment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/sync-interval")
def update_sync_interval(request: Request, interval: int = Query(..., ge=5, le=3600)):
    """Update the background sync interval for the current user."""
    user_email = _get_authenticated_user_email(request)
    _user_sync_intervals[user_email] = interval
    logger.info(f"⏳ [Settings] Sync interval for {user_email} updated to {interval}s")
    return {"status": "success", "interval": interval}

@app.post("/process")
def process_emails(request: Request):
    user_email = _get_authenticated_user_email(request)
    # Force-clear the in-memory cache so we re-fetch from Gmail with fresh logic
    key = _user_key(user_email)
    lock = _get_user_lock(user_email)
    with lock:
        _dynamic_cache_df_by_user.pop(key, None)
        _dynamic_cache_at_by_user.pop(key, None)
    
    # Use the High-Reliability sync logic
    _refresh_dynamic_cache(user_email, force_refresh=True)
    return {"status": "emails processed", "source_mode": "dynamic", "mailbox": user_email}


@app.post("/process-demo")
def process_demo_emails(request: Request):
    """Backwards-compatible alias for dynamic processing."""
    user_email = _get_authenticated_user_email(request)
    _refresh_dynamic_cache(user_email, force_refresh=True)
    return {"status": "emails processed", "source_mode": "dynamic", "mailbox": user_email}


class DemoInboxSeedResponse(BaseModel):
    success: bool
    message: str
    stats: Dict[str, Any]


@app.post("/emails/seed-demo", response_model=DemoInboxSeedResponse)
def seed_demo_emails_to_inbox(request: Request):
    """Send demo mails into configured Gmail inbox so dynamic fetch can read them."""
    try:
        user_email = _get_authenticated_user_email(request)
        stats = _send_demo_emails_to_gmail_inbox(user_email)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to seed demo emails: {exc}")

    return DemoInboxSeedResponse(
        success=True,
        message="Demo emails sent to inbox successfully",
        stats=stats,
    )


@app.post("/emails/seed-excel", response_model=DemoInboxSeedResponse)
def seed_excel_emails_to_inbox(
    request: Request,
    only_demo: bool = Query(True, description="If true, seed only rows where is_demo is true."),
    limit: int = Query(0, ge=0, description="Maximum number of rows to seed. 0 means all matching rows."),
):
    """Send rows from grievances.xlsx into configured Gmail inbox so dynamic fetch can read them."""
    try:
        user_email = _get_authenticated_user_email(request)
        stats = _send_excel_emails_to_gmail_inbox(user_email, only_demo=only_demo, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to seed Excel emails: {exc}")

    return DemoInboxSeedResponse(
        success=True,
        message="Excel emails sent to inbox successfully",
        stats=stats,
    )


@app.post("/emails/cleanup-seeded", response_model=DemoInboxSeedResponse)
def cleanup_seeded_emails_in_inbox(
    request: Request,
    dry_run: bool = Query(True, description="If true, only report matches without moving emails to trash."),
    only_inbox: bool = Query(True, description="If true, clean only INBOX; if false, include all labels."),
    limit: int = Query(0, ge=0, description="Maximum number of seeded emails to evaluate. 0 means all matches."),
):
    """Move seeded demo emails to trash based on subject prefix."""
    try:
        user_email = _get_authenticated_user_email(request)
        stats = _cleanup_seeded_emails_in_gmail(user_email, dry_run=dry_run, limit=limit, only_inbox=only_inbox)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup seeded emails: {exc}")

    message = "Seeded email cleanup preview generated" if dry_run else "Seeded emails moved to trash"
    return DemoInboxSeedResponse(
        success=True,
        message=message,
        stats=stats,
    )


class DemoPolicySyncResponse(BaseModel):
    success: bool
    message: str
    stats: Dict[str, Any]


@app.post("/policies/load-demo", response_model=DemoPolicySyncResponse)
def load_demo_policies():
    """Rebuild policy_chunks.json and FAISS from the demo policy PDFs."""
    try:
        stats = _sync_demo_policy_pdfs(force_index_rebuild=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load demo policies: {exc}")

    return DemoPolicySyncResponse(
        success=True,
        message="Demo policy PDFs loaded and indexed successfully",
        stats=stats,
    )

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(request: ChatRequest, fastapi_req: Request):
    print("📥 CHAT MESSAGE:", repr(request.message))

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    user_email = _get_authenticated_user_email(fastapi_req)
    answer = get_chatbot_response(request.message, user_email)

    print("🤖 CHAT ANSWER:", repr(answer))
    return {"reply": answer}

@app.get("/dashboard")
def dashboard(request: Request):
    user_email = _get_authenticated_user_email(request)
    df = _get_active_dataframe(user_email)
    if df.empty:
        return {"total": 0, "fresh": 0, "followup": 0}
    
    return {
        "total": len(df),
        "fresh": int((df["mail_type"] == "Fresh").sum()),
        "followup": int((df["mail_type"] == "Follow-up").sum()),
    }

@app.get("/download/attachment/{filename}")
def download_attachment(filename: str):
    """Download an actual attachment file (PDF, DOCX, Excel, etc.)"""
    file_path = os.path.join("./attachments", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Determine media type based on extension
    ext = filename.lower().split('.')[-1]
    media_types = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls': 'application/vnd.ms-excel',
        'txt': 'text/plain',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    # Extract original filename (remove hash prefix)
    original_name = '_'.join(filename.split('_')[1:]) if '_' in filename else filename
    
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=original_name
    )

@app.get("/api/emails/attachments/inline/{gmail_id}/{cid}")
def get_inline_attachment(gmail_id: str, cid: str, request: Request):
    """Proxy inline images securely through our backend to avoid CORS/Auth issues"""
    user_email = _get_authenticated_user_email(request)
    service = _get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401, detail="Gmail login required")
        
    try:
        msg = service.users().messages().get(userId='me', id=gmail_id).execute()
        
        def find_part_by_cid(parts, target_cid):
            for part in parts:
                if part.get("headers"):
                    headers = {h["name"].lower(): h["value"] for h in part["headers"]}
                    if "content-id" in headers and target_cid in headers["content-id"]:
                        return part
                if "parts" in part:
                    found = find_part_by_cid(part["parts"], target_cid)
                    if found:
                        return found
            return None
            
        target_part = None
        if "payload" in msg:
            if "parts" in msg["payload"]:
                target_part = find_part_by_cid(msg["payload"]["parts"], cid)
                
        if not target_part:
            raise HTTPException(status_code=404, detail="Attachment not found")
            
        attachment_id = target_part.get("body", {}).get("attachmentId")
        if not attachment_id:
             if target_part.get("body", {}).get("data"):
                 import base64
                 data = base64.urlsafe_b64decode(target_part["body"]["data"])
                 return Response(content=data, media_type=target_part.get("mimeType", "image/jpeg"))
             raise HTTPException(status_code=404, detail="Attachment ID not found")
             
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=gmail_id, id=attachment_id
        ).execute()
        
        import base64
        data = base64.urlsafe_b64decode(attachment["data"])
        from fastapi.responses import Response
        return Response(content=data, media_type=target_part.get("mimeType", "image/jpeg"))
        
    except Exception as e:
        logger.error(f"Error serving inline image {cid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/email/{eml_filename}")
def download_eml(eml_filename: str):
    """Download the original .eml file if needed"""
    file_path = os.path.join(FILES_DIR, eml_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Email file not found")
    return FileResponse(
        file_path,
        media_type="message/rfc822",
        filename=eml_filename
    )


class PolicyUploadResponse(BaseModel):
    success: bool
    message: str
    stats: Dict[str, Any]


def _slugify_policy_id(raw_name: str) -> str:
    base = Path(raw_name).stem if raw_name else "policy"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base).strip("_")
    return base or "policy"


def _load_policy_chunks() -> list[Dict[str, Any]]:
    if not CHUNKS_PATH.exists():
        return []
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _save_policy_chunks(chunks: list[Dict[str, Any]]) -> None:
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)


def _rebuild_index_from_chunks(chunks: list[Dict[str, Any]]) -> None:
    texts = [chunk.get("text", "") for chunk in chunks if chunk.get("text")]

    if not texts:
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    embeddings = embedder.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    embeddings = np.asarray(embeddings).astype("float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss.write_index(index, str(INDEX_PATH))


def _remove_policy_chunks(policy_id: str) -> tuple[list[Dict[str, Any]], int]:
    chunks = _load_policy_chunks()
    retained = [c for c in chunks if str(c.get("policy_id", "")) != policy_id]
    removed = len(chunks) - len(retained)

    if removed:
        _save_policy_chunks(retained)
        _rebuild_index_from_chunks(retained)

    return retained, removed


def _policy_file_exists(policy_id: str) -> bool:
    return _resolve_policy_file_path(policy_id) is not None


def _resolve_policy_file_path(policy_id: str) -> Path | None:
    uploaded_path = POLICY_DIR / f"{policy_id}.pdf"
    if uploaded_path.exists():
        return uploaded_path

    demo_path = DEMO_POLICY_DIR / f"{policy_id}.pdf"
    if demo_path.exists():
        return demo_path

    return None


@app.post("/policies/upload", response_model=PolicyUploadResponse)
async def upload_policy(file: UploadFile = File(...)):
    """Upload a PDF policy and ingest it into policy_chunks.json + FAISS index."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    policy_id = _slugify_policy_id(file.filename)
    policy_path = POLICY_DIR / f"{policy_id}.pdf"
    was_existing = policy_path.exists()

    try:
        with open(policy_path, "wb") as out_file:
            shutil.copyfileobj(file.file, out_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")
    finally:
        await file.close()

    try:
        # Keep one canonical entry per policy_id by replacing previous chunks on update.
        _remove_policy_chunks(policy_id)

        stats = ingest_policy_document(
            file_path=str(policy_path),
            policy_id=policy_id,
            section_title="General",
        )
        stats["is_update"] = was_existing
        stats["policy_id"] = policy_id

        reload_retriever_data(force=True)

        return PolicyUploadResponse(
            success=True,
            message="Policy uploaded and indexed successfully",
            stats=stats,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest policy: {str(e)}")


@app.get("/policies")
def list_policies():
    """List policies currently indexed in RAG with per-policy chunk counts."""
    chunks = _load_policy_chunks()
    by_policy: Dict[str, int] = {}

    for chunk in chunks:
        pid = str(chunk.get("policy_id", "")).strip()
        if pid:
            by_policy[pid] = by_policy.get(pid, 0) + 1

    policies = []
    for policy_id, chunk_count in sorted(by_policy.items(), key=lambda x: x[0].lower()):
        file_exists = _policy_file_exists(policy_id)
        policies.append(
            {
                "id": policy_id,
                "chunk_count": chunk_count,
                "status": "indexed" if file_exists else "indexed_no_file",
            }
        )

    return {"policies": policies}


@app.get("/policies/{policy_id}")
def get_policy_pdf(policy_id: str):
    """Download/view original policy PDF by policy_id."""
    policy_file = _resolve_policy_file_path(policy_id)
    if policy_file is None:
        raise HTTPException(status_code=404, detail="Policy file not found")

    return FileResponse(
        str(policy_file),
        media_type="application/pdf",
        filename=policy_file.name,
    )


@app.delete("/policies/{policy_id}")
def delete_policy(policy_id: str):
    """Delete a policy PDF and all associated chunks, then rebuild FAISS."""
    policy_file = POLICY_DIR / f"{policy_id}.pdf"
    had_file = policy_file.exists()
    if policy_file.exists():
        policy_file.unlink()

    _, removed_chunks = _remove_policy_chunks(policy_id)
    reload_retriever_data(force=True)

    if removed_chunks == 0 and not had_file:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {
        "success": True,
        "message": f"Policy '{policy_id}' removed",
        "removed_chunks": removed_chunks,
    }


# Request model for reply generation
class GenerateReplyRequest(BaseModel):
    email_content: str
    email_subject: str = ""
    sender: str = ""
    category: str = ""
    attachment_content: str = ""


class GenerateReplyResponse(BaseModel):
    suggested_reply: str
    generation_mode: str = "simple_stabilized"
    status: str = "ok"
    evidence: list[Dict[str, Any]] = []
    trust_score: float | None = None
    trust_label: str | None = None
    trust_visibility: Dict[str, Any] = {}
    retrieval: Dict[str, Any] = {}
    grounding_report: Dict[str, Any] = {}
    sentence_evidence: list[Dict[str, Any]] = []
    explainability: Dict[str, Any] = {}
    internal_view: Dict[str, Any] = {}
    external_view: Dict[str, Any] = {}


class SendReplyRequest(BaseModel):
    to_email: str
    reply_text: str
    original_subject: str = ""
    thread_id: str = None
    in_reply_to: str = None

class ComposeRequest(BaseModel):
    to_email: str
    subject: str
    body: str

class SendReplyResponse(BaseModel):
    success: bool
    message: str
    to_email: str
    subject: str
    gmail_id: str = None


def _build_reply_subject(original_subject: str) -> str:
    base = str(original_subject or "").strip()
    if not base:
        return "Reply from Education Department"
    if base.lower().startswith("re:"):
        return base
    return f"RE: {base}"


@app.post("/test-api-keys")
def test_api_keys():
    """Test both MAIN and PRIORITY Gemini API keys."""
    main_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    priority_key = os.getenv("PRIORITY_GOOGLE_API_KEY") or os.getenv("PRIORITY_GEMINI_API_KEY")

    results = {
        "main": {"status": "missing", "message": "No key configured"},
        "priority": {"status": "missing", "message": "No key configured"}
    }

    # Test MAIN key
    if main_key and "your_google_api_key" not in main_key.lower():
        try:
            client = genai.Client(api_key=main_key)
            client.models.generate_content(model="gemini-2.0-flash", contents="Hello")
            results["main"] = {"status": "success", "message": "Key is valid"}
        except Exception as e:
            results["main"] = {"status": "error", "message": str(e)}
    
    # Test PRIORITY key
    if priority_key and "your_google_api_key" not in priority_key.lower():
        try:
            client = genai.Client(api_key=priority_key)
            client.models.generate_content(model="gemini-2.0-flash", contents="Hello")
            results["priority"] = {"status": "success", "message": "Key is valid"}
        except Exception as e:
            results["priority"] = {"status": "error", "message": str(e)}
    elif main_key and not priority_key:
        results["priority"] = {"status": "success", "message": "Using Main key (Valid)"} if results["main"]["status"] == "success" else results["main"]

    return results


@app.post("/generate-reply")
def generate_reply(request: GenerateReplyRequest) -> GenerateReplyResponse:
    """Generate AI-powered suggested reply using RAG system"""
    try:
        logger.info(
            f"Generating reply | sender={request.sender} | subject={request.email_subject}"
        )

        reply_bundle = generate_suggested_reply_with_evidence(
            email_content=request.email_content,
            email_subject=request.email_subject,
            sender=request.sender,
            category=request.category,
            attachment_content=request.attachment_content
        )
        return GenerateReplyResponse(**reply_bundle)
    except Exception as e:
        print(f"Error generating reply: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate reply: {str(e)}")


@app.post("/emails/compose", response_model=SendReplyResponse)
def compose_new_email(request: Request, payload: ComposeRequest):
    user_email = _get_authenticated_user_email(request)
    recipient = parseaddr(payload.to_email)[1].strip()
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    
    gmail_id = _send_email_via_gmail_api(user_email, recipient, payload.subject, payload.body)
    if gmail_id:
        return SendReplyResponse(
            success=True,
            message="Email sent successfully",
            to_email=recipient,
            subject=payload.subject,
            gmail_id=gmail_id
        )
    raise HTTPException(status_code=500, detail="Failed to send email via Gmail API")

@app.post("/send-reply", response_model=SendReplyResponse)
def send_reply_email(request: Request, payload: SendReplyRequest):
    user_email = _get_authenticated_user_email(request)
    recipient = parseaddr(payload.to_email)[1].strip()
    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient email is required")

    body = str(payload.reply_text or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Reply text is required")

    subject = _build_reply_subject(payload.original_subject)

    gmail_id = _send_email_via_gmail_api(
        user_email, 
        recipient, 
        subject, 
        body, 
        thread_id=payload.thread_id, 
        in_reply_to=payload.in_reply_to
    )

    if gmail_id:
        # 🔥 UPDATE LOCAL CACHE & DB
        key = _user_key(user_email)
        lock = _get_user_lock(user_email)
        with lock:
            cached_df = _dynamic_cache_df_by_user.get(key)
            if cached_df is not None:
                # Group update: Mark the whole thread as replied if applicable
                if payload.thread_id:
                    mask = (cached_df["thread_id"] == payload.thread_id)
                else:
                    mask = (cached_df["sender_email"] == recipient)
                cached_df.loc[mask, "replied"] = True
                _dynamic_cache_df_by_user[key] = cached_df
                
                # Update SQLite DB for persistence
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    if payload.thread_id:
                        cursor.execute("UPDATE emails SET replied = 1 WHERE thread_id = ? AND user_email = ?", (payload.thread_id, user_email))
                    else:
                        cursor.execute("UPDATE emails SET replied = 1 WHERE sender_email = ? AND user_email = ?", (recipient, user_email))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"⚠️ Failed to update replied status in DB: {e}")
                
        return SendReplyResponse(
            success=True,
            message="Reply email sent successfully",
            to_email=recipient,
            subject=subject,
            gmail_id=gmail_id
        )

    raise HTTPException(
        status_code=500,
        detail="Google OAuth is required to send replies. Reconnect Gmail through the app.",
    )


@app.post("/emails/{email_id}/trash")
def trash_email(email_id: str, request: Request):
    """Move a grievance message to the local Trash DB and then to Gmail Trash"""
    user_email = _get_authenticated_user_email(request)
    service = _get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401, detail="Gmail login required.")

    # 1. Update Persistent Local DB (INSTANT atomic update)
    mark_as_trashed(user_email, email_id, True)

    # 2. Update In-Memory cache
    key = _user_key(user_email)
    lock = _get_user_lock(user_email)
    with lock:
        df = _dynamic_cache_df_by_user.get(key)
        if df is not None:
             mask = (df["email_id"] == email_id)
             if mask.any():
                 row = df.loc[mask].iloc[0]
                 gmail_id = row.get("gmail_id")
                 
                 # Optimistically remove or mark as trashed in cache
                 df = df.loc[~mask].reset_index(drop=True)
                 _dynamic_cache_df_by_user[key] = df
                 
                 # 3. Call Gmail Trash in background (slow)
                 if gmail_id:
                     try:
                         service.users().messages().trash(userId="me", id=gmail_id).execute()
                     except Exception as e:
                         print(f"⚠️ Gmail Trash failed: {e}")
        
    return {"success": True, "message": "Email moved to Trash locally and in Gmail."}


@app.post("/emails/{email_id}/untrash")
def untrash_email(email_id: str, request: Request):
    """Restore a grievance message from the local Trash DB and Gmail Trash"""
    user_email = _get_authenticated_user_email(request)
    service = _get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401, detail="Gmail login required.")

    # 1. Update Persistent Local DB (INSTANT atomic update) - SET is_inbox = 1
    # We use a direct DB query here to ensure is_inbox is explicitly set, 
    # instead of just relying on mark_as_trashed which doesn't know the exact previous state.
    from database_api import DB_PATH
    import sqlite3
    
    gmail_id = None
    is_demo = 0
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        # Verify ownership and get details
        cursor.execute("SELECT gmail_id, is_demo FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        row = cursor.fetchone()
        
        if row:
            gmail_id = row[0]
            is_demo = row[1]
            
            # Execute explicit restore flags
            cursor.execute(
                "UPDATE emails SET is_trashed = 0, is_inbox = 1, category = 'miscellaneous' WHERE id = ? AND user_email = ?", 
                (email_id, user_email)
            )
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Local Untrash failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update local database.")

    if not row:
         raise HTTPException(status_code=404, detail="Email not found or access denied.")

    message_appendix = ""

    # 2. Re-sync with Gmail Trash directory directly
    if is_demo:
         message_appendix = " (Note: This is a local Demo email, so it does not exist in your real Gmail account.)"
    elif gmail_id:
        try:
            # 2a. Remove from Trash
            service.users().messages().untrash(userId="me", id=gmail_id).execute()
            
            # 2b. Explicitly add INBOX label to ensure it appears in the Gmail app Inbox
            # This fixes the issue where untrash only archives the message.
            service.users().messages().modify(
                userId="me", 
                id=gmail_id, 
                body={"addLabelIds": ["INBOX"]}
            ).execute()
        except HttpError as err:
            error_details = json.loads(err.content.decode('utf-8'))
            if error_details.get("error", {}).get("code") == 404:
                 print(f"⚠️ Gmail Untrash failed: Email not found in Gmail. It might have been permanently deleted.")
                 message_appendix = " (Warning: This email could not be found in your actual Gmail account. It may have been permanently deleted there, but is now restored locally.)"
            else:
                 print(f"⚠️ Gmail Untrash failed: {err}")
                 message_appendix = " (Warning: Failed to sync restoration with Google servers. Check your Gmail trash manually.)"
        except Exception as e:
            print(f"⚠️ Gmail Untrash failed: {e}")
            message_appendix = " (Warning: Failed to communicate with Google servers.)"
    else:
        message_appendix = " (Warning: Missing Gmail ID. Could not restore in Gmail app.)"

    # 3. Aggressively purge cache so the next UI GET call physically restages the email into Inbox array
    key = _user_key(user_email)
    lock = _get_user_lock(user_email)
    with lock:
        if key in _dynamic_cache_at_by_user:
            _dynamic_cache_at_by_user[key] = None

    return {"success": True, "message": f"Email restored to Inbox.{message_appendix}"}


# ---------------- RISC WEBHOOK ----------------

@app.post("/risc/webhook")
async def risc_webhook(request: Request):
    """
    Handle Google Cross-Account Protection (RISC) security event notifications.
    Standard: https://developers.google.com/identity/protocols/risc
    """
    try:
        body = await request.body()
        token = body.decode("utf-8")
        
        # 1. Get Google's RISC configuration
        risc_config_uri = 'https://accounts.google.com/.well-known/risc-configuration'
        risc_config = requests.get(risc_config_uri).json()
        
        # 2. Get public keys for validation
        google_certs = requests.get(risc_config['jwks_uri']).json()
        
        # 3. Decode & Validate JWT
        # aud should be your client ID. Since we have multiple components, we accept all known client IDs.
        # iss should match risc_config['issuer']
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        
        # We use PyJWT with the JWK set
        # Note: In a production environment, you should cache the certs.
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        public_key = None
        for key in google_certs['keys']:
            if key['kid'] == kid:
                from jwt.algorithms import RSAAlgorithm
                public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                break
        
        if not public_key:
            raise Exception("Public key not found in Google's certs")

        # Validate signature, issuer, and audience
        # We don't check expiration for RISC events per Google spec
        decoded = jwt.decode(
            token, 
            public_key, 
            algorithms=['RS256'],
            audience=client_id,
            issuer=risc_config['issuer'],
            options={"verify_exp": False}
        )
        
        # 4. Handle events
        events = decoded.get("events", {})
        for event_type, event_data in events.items():
            subject = event_data.get("subject", {})
            user_email = subject.get("email") or subject.get("sub")
            
            if not user_email:
                continue
                
            # Types: https://developers.google.com/identity/protocols/risc#supported_event_types
            if "account-disabled" in event_type or "sessions-revoked" in event_type or "tokens-revoked" in event_type:
                from database_api import revoke_user_session
                reason = event_data.get("reason", "Google Security Event")
                revoke_user_session(user_email, f"RISC Event: {event_type} | {reason}")
                print(f"🛑 SECURITY REVOCATION: {user_email} due to {event_type}")

        # Google expects 202 Accepted
        from fastapi import Response
        return Response(status_code=202)
        
    except Exception as e:
        print(f"⚠️ RISC Webhook Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Security Event Token")


# ---------------- MAIN ----------------
if __name__ == "__main__":
    init_db()  # Initialize SQLite
    
    # NEW: Automatically repair/reclassify existing emails on startup using the latest weighted logic
    try:
        reclassify_all_stored_emails(classify_grievance)
    except Exception as e:
        logger.error(f"⚠️ Startup reclassification failed: {e}")
        
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
