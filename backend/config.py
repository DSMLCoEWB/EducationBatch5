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
AI_PREFER_LOCAL = os.getenv("AI_PREFER_LOCAL", "true").lower() == "true"
PRIMARY_LOCAL_MODEL = os.getenv("PRIMARY_LOCAL_MODEL", "qwen3.5:2b").strip()

# --- AI MODEL HANDSHAKE ---
_fallback_models_raw = os.getenv("AI_FALLBACK_MODELS", "").strip()
if _fallback_models_raw:
    ULTIMATE_FALLBACK_LIST = [m.strip() for m in _fallback_models_raw.split(",") if m.strip()]
else:
    ULTIMATE_FALLBACK_LIST = [
        "models/gemini-3.1-flash-lite",
        "models/gemini-flash-latest",
        "models/gemini-3-flash-preview",
        "models/gemini-2.5-flash",
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

_vision_fallback_raw = os.getenv("VISION_FALLBACK_MODELS", "").strip()
if _vision_fallback_raw:
    VISION_FALLBACK_LIST = [m.strip() for m in _vision_fallback_raw.split(",") if m.strip()]
else:
    VISION_FALLBACK_LIST = [
        "models/gemini-2.5-flash",
        "models/gemini-3.1-flash-lite",
        "models/gemini-flash-latest",
        "models/gemini-3-flash-preview", 
        "models/gemini-2.5-flash-lite"
    ]

# --- GRIEVANCE TAXONOMY ---
CATEGORIES = {
    "Suspension / Disciplinary": [
        "suspension", "suspended", "suspend",
        "chargesheet", "charge sheet", "charge-sheet",
        "disciplinary", "discipline", "disciplinary action",
        "departmental proceeding", "departmental proceedings",
        "departmental inquiry", "departmental enquiry",
        "dismissal", "dismissed", "termination",
        "punishment", "penalty", "penal action",
        "misconduct", "violation", "breach",
        "show cause", "show-cause", "showcause",
        "investigation",
        "suspended employee", "suspended staff",
        "suspended official", "suspended officer",
        "suspension status", "suspension order"
    ],

    "Legal Issues": [
        "fir", "first information report",
        "arrest", "arrested", "arresting",
        "police", "police case", "police complaint",
        "court", "court case", "court order",
        "legal", "legal case", "legal matter",
        "litigation", "lawsuit", "suit",
        "criminal", "criminal case", "criminal complaint",
        "warrant", "bail", "custody",
        "judgment", "judgement", "verdict",
        "hearing", "trial", "proceedings",
        "advocate", "lawyer", "attorney",
        "petition", "appeal", "writ",
        "contempt", "injunction", "stay order"
    ],

    "RTI Matters": [
        "rti", "right to information",
        "information request", "rti application",
        "rti appeal", "rti reply",
        "public information officer", "pio",
        "first appellate authority", "faa",
        "rti response", "rti filing",
        "disclosure", "transparency",
        "rti order", "rti case"
    ],

    "CMO Issues": [
        "cmo", "chief minister office",
        "chief minister's office", "cm office",
        "cm complaint", "cm grievance",
        "cm cell", "cmo reference",
        "cmo complaint", "cmo matter",
        "referred by cmo", "cmo letter"
    ],

    "Semester / Examination": [
        "semester", "semesters",
        "exam", "exams", "examination", "examinations",
        "marks", "mark", "grade", "grades",
        "result", "results",
        "admit card", "admitcard", "admission card",
        "backlog", "backlogs", "back paper",
        "supplementary", "supplementary exam",
        "re-examination", "reexamination",
        "cgpa", "sgpa", "gpa",
        "pass", "fail", "failed",
        "detention", "promoted",
        "credit", "credits", "attendance",
        "marksheet", "mark sheet", "transcript"
    ],

    "Scholarship & Fee Concession": [
        "scholarship", "scholarships",
        "svmcm", "swami vivekananda",
        "student credit card", "credit card loan",
        "oasis", "oasis scholarship",
        "merit cum means", "mcm",
        "freeship", "free ship",
        "fee waiver", "fee concession",
        "fee exemption", "tuition waiver",
        "stipend", "financial aid",
        "minority scholarship", "sc scholarship", "st scholarship",
        "obc scholarship", "post matric", "pre matric"
    ],

    "Purchase / Procurement Issues": [
        "purchase", "procurement", "procure",
        "tender", "tenders", "e-tender",
        "quotation", "quotations", "rfq",
        "supply", "supplier", "vendor",
        "contract", "work order",
        "gemportal", "gem portal", "government e-marketplace",
        "rate contract", "rate contracts",
        "bill", "bills", "invoice", "invoices",
        "payment pending", "due payment",
        "purchase order", "purchase committee"
    ],

    "Cash Issues": [
        "cash", "cash misappropriation",
        "embezzlement", "misuse of funds",
        "financial irregularity", "financial fraud",
        "fund diversion", "diversion of funds",
        "accounts", "accountant",
        "audit", "audit report", "audit objection",
        "treasury", "treasury challan",
        "grant", "grant utilization", "utilization certificate",
        "budget", "expenditure", "overspending",
        "misappropriation", "fraud", "corruption"
    ],

    "Anti-Ragging Complaints": [
        "ragging", "anti-ragging", "anti ragging",
        "rag", "ragged", "ragging complaint",
        "ragging incident", "ragging case",
        "ugc anti ragging", "aicte anti ragging",
        "senior junior", "bullying", "harassment",
        "hostel ragging", "campus ragging",
        "ragging committee", "anti ragging committee"
    ],

    "Accreditation & Ranking": [
        "naac", "nba", "nirf",
        "accreditation", "accredited",
        "ranking", "rankings",
        "naac grade", "naac score", "naac visit",
        "nba accreditation", "nba status",
        "nirf ranking", "nirf submission",
        "iqac", "internal quality assurance",
        "peer team", "accreditation report",
        "self study report", "ssr",
        "institutional grading"
    ],

    "Service Matters": [
        "transfer", "transferred", "transferring",
        "posting", "posted",
        "promotion", "promoted",
        "service book", "service record",
        "pay fixation", "salary", "increment",
        "appointment", "appointed",
        "deputation", "deputed",
        "leave", "leave application", "leave sanction",
        "retirement", "pension", "pensionary",
        "gratuity", "provident fund", "gpf", "epf",
        "seniority", "seniority list",
        "confirmation", "confirmed",
        "probation", "probationary",
        "regularization", "regularized",
        "pay scale", "pay revision", "arrear",
        "service matter", "service dispute"
    ],

    "Appointment Issues": [
        "appointment", "appointed", "appointment order",
        "recruitment", "recruited",
        "selection", "selection process",
        "interview", "walk-in interview",
        "advertisement", "vacancy", "vacancies",
        "joining", "joining letter", "joining date",
        "offer letter", "appointment letter",
        "contractual", "ad hoc", "adhoc",
        "part time", "guest lecturer", "guest faculty",
        "direct recruitment", "dr", "merit list"
    ],

    "Transfer Cases": [
        "transfer", "transfer order", "transfer case",
        "mutual transfer", "transfer request",
        "inter district transfer", "intra district transfer",
        "transfer posting", "place of posting",
        "transfer grievance", "transfer complaint",
        "transfer list", "transfer policy",
        "hardship transfer", "medical grounds transfer",
        "transfer cancellation", "transfer stay"
    ],

    "Inspection Matters": [
        "inspection", "inspected", "inspector",
        "inspection report", "inspection team",
        "inspection visit", "inspection findings",
        "site inspection", "physical inspection",
        "compliance", "compliance report",
        "deficiency", "deficiencies",
        "inspection committee", "inspection order",
        "surprise inspection", "routine inspection"
    ],

    "Seat Matrix Issues": [
        "seat matrix", "seat matrices",
        "seats", "intake", "intake capacity",
        "seat allocation", "seat allotment",
        "seat increase", "seat reduction",
        "additional seats", "excess seats",
        "counselling seats", "wbjeeb", "jelet",
        "lateral entry", "seat approval",
        "aicte approval", "university affiliation",
        "affiliated seats", "approved intake"
    ],
}

PRIORITY_KEYWORDS = {
    "0": ["urgent", "critical", "cmo", "emergency", "immediate", "legal", "court", "salary", "pension", "arrear", "fixation", "seniority"],
    "1": ["suspension", "disciplinary", "chargesheet", "misconduct", "ragging", "anti-ragging", "anti ragging", "transfer", "posting", "deputation"],
    "2": ["exam", "semester", "result", "marksheet", "admit", "scholarship", "svmcm", "oasis", "fee"],
    "3": ["general", "query", "status", "acknowledge"]
}

# --- RAG CONFIGURATION ---
INDEX_PATH = DATA_DIR / "rag_index.faiss"
CHUNKS_PATH = DATA_DIR / "policy_chunks.json"
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.30"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", RAG_MIN_SCORE))
RAG_FINAL_LIMIT = int(os.getenv("RAG_FINAL_LIMIT", "3"))
RAG_MAX_UNIQUE_SECTIONS = int(os.getenv("RAG_MAX_UNIQUE_SECTIONS", "0"))

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
