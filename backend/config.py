import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- ENVIRONMENT & VERSIONING ---
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}

# --- DIRECTORY STRUCTURE ---
BASE_DIR = Path(__file__).parent
FILES_DIR = BASE_DIR / "files"
EXCEL_FILE = BASE_DIR / "data" / "grievances.xlsx"
POLICY_DIR = BASE_DIR / "policies"
DEMO_POLICY_DIR = BASE_DIR / "demo_policies"
ATTACHMENTS_DIR = BASE_DIR / "attachments"
DATA_DIR = BASE_DIR / "data"

# Ensure required directories exist
for d in [FILES_DIR, DATA_DIR, POLICY_DIR, DEMO_POLICY_DIR, ATTACHMENTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- GOOGLE OAUTH CONFIGURATION ---
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback").strip()
GOOGLE_OAUTH_ENCRYPTION_KEY = os.getenv("GOOGLE_OAUTH_ENCRYPTION_KEY", "").strip()
GOOGLE_OAUTH_TOKENS_DIR = DATA_DIR / "oauth_tokens"
GOOGLE_OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)

_cookie_secure_raw = os.getenv("GOOGLE_OAUTH_COOKIE_SECURE", "false").strip().lower()
GOOGLE_OAUTH_COOKIE_SECURE = (_cookie_secure_raw == "true") or (not IS_PRODUCTION) # False in dev for simplicity if not set

GOOGLE_OAUTH_SUCCESS_REDIRECT_URL = os.getenv("GOOGLE_OAUTH_SUCCESS_REDIRECT_URL", "").strip()
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]

# --- SECURITY & SESSIONS ---
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", GOOGLE_OAUTH_ENCRYPTION_KEY).strip()
SEEDED_SUBJECT_PREFIX = "[AICOE-SEED]"

# Relax oauthlib strict scope checking to allow Google to inject 'openid' without crashing
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# --- DATABASE ---
DB_PATH = DATA_DIR / "grievances.db"

# --- SYNC & PERFORMANCE ---
SYNC_ENABLED = os.getenv("SYNC_ENABLED", "true").lower() == "true"
GMAIL_CALLS_PER_MINUTE_LIMIT = int(os.getenv("GMAIL_CALLS_PER_MINUTE_LIMIT", "50"))
SYNC_JITTER_SECONDS = float(os.getenv("SYNC_JITTER_SECONDS", "60.0"))
SYNC_MAX_BACKOFF_SECONDS = float(os.getenv("SYNC_MAX_BACKOFF_SECONDS", "3600.0"))
GMAIL_SYNC_INTERVAL_SECONDS = int(os.getenv("GMAIL_SYNC_INTERVAL_SECONDS", "300"))
MANUAL_SYNC_COOLDOWN_SECONDS = int(os.getenv("MANUAL_SYNC_COOLDOWN_SECONDS", "120"))
GMAIL_FULL_SYNC_DAYS = int(os.getenv("GMAIL_FULL_SYNC_DAYS", "14"))

# --- CACHING & MEMORY ---
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
MAX_CACHE_ENTRIES = 20 if IS_PRODUCTION else 100
MAX_DF_ROWS = 5000 if IS_PRODUCTION else 20000
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "60"))
# Support both names for sync interval to match template
GMAIL_SYNC_INTERVAL_SECONDS = int(os.getenv("GMAIL_SYNC_INTERVAL_SECONDS", os.getenv("DYNAMIC_AUTO_REFRESH_SECONDS", "300")))

# --- AI & ANALYTICS ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", GOOGLE_API_KEY).strip()
CHATBOT_GEMINI_API_KEY = os.getenv("CHATBOT_GEMINI_API_KEY", GEMINI_API_KEY).strip()
PRIORITY_GOOGLE_API_KEY = os.getenv("PRIORITY_GOOGLE_API_KEY", GEMINI_API_KEY).strip()

# --- AI MODEL HANDSHAKE ---
_fallback_models_raw = os.getenv("AI_FALLBACK_MODELS", "").strip()
if _fallback_models_raw:
    ULTIMATE_FALLBACK_LIST = [m.strip() for m in _fallback_models_raw.split(",") if m.strip()]
else:
    ULTIMATE_FALLBACK_LIST = [
        "models/gemini-3.1-flash-lite-preview", 
        "models/gemini-flash-latest",
        "models/gemini-3-flash-preview", 
        "models/gemini-2.5-flash-lite",
        "models/gemma-4-31b-it",
        "models/gemma-4-26b-a4b-it",
        "models/gemma-3-27b-it",
        "models/gemma-3-12b-it",
        "models/gemma-3-4b-it",
        "models/gemma-3n-e2b-it",
        "models/gemma-3-1b-it",
        "models/gemini-robotics-er-1.6-preview",
        "models/gemini-robotics-er-1.5-preview"
    ]

VISION_FALLBACK_LIST = [
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-flash-latest",
    "models/gemini-3-flash-preview", 
    "models/gemini-2.5-flash-lite"
]

# --- GRIEVANCE TAXONOMY ---
from classifier import CATEGORIES

PRIORITY_KEYWORDS = {
    "0": ["urgent", "critical", "cmo", "emergency", "immediate", "legal", "court"],
    "1": ["salary", "pension", "arrear", "fixation", "seniority"],
    "2": ["suspension", "disciplinary", "chargesheet", "misconduct", "ragging", "anti-ragging", "anti ragging"],
    "3": ["transfer", "posting", "deputation"],
    "4": ["exam", "semester", "result", "marksheet", "admit"],
    "5": ["scholarship", "svmcm", "oasis", "fee"],
    "6": ["general", "query", "status", "acknowledge"]
}

# --- RAG CONFIGURATION ---
INDEX_PATH = DATA_DIR / "rag_index.faiss"
CHUNKS_PATH = DATA_DIR / "policy_chunks.json"
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.40"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", RAG_MIN_SCORE))
RAG_FINAL_LIMIT = int(os.getenv("RAG_FINAL_LIMIT", "3"))

# --- SURGICAL RAG "3+2" PARAMETERS ---
RAG_UNREPLIED_MAX = int(os.getenv("RAG_UNREPLIED_MAX", "3"))
RAG_ANCHOR_DEPTH = int(os.getenv("RAG_ANCHOR_DEPTH", "2"))

# ---------- 📊 PRIORITY LLM RATE LIMITING ----------
PRIORITY_LLM_MAX_CALLS = int(os.getenv("PRIORITY_LLM_MAX_CALLS", "1"))
PRIORITY_LLM_WINDOW_SECONDS = int(os.getenv("PRIORITY_LLM_WINDOW_SECONDS", "60"))

AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "15"))

COLUMNS = [
    "email_id", "gmail_id", "thread_id", "sender", "sender_email", 
    "subject", "date", "has_attachment", "attachments", 
    "category", "mail_type", "priority", "is_demo", "replied",
    "is_trashed", "is_inbox", "is_sent", "is_priority_refined"
]
