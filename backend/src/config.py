import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- ENVIRONMENT & VERSIONING ---
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}

# --- DIRECTORY STRUCTURE ---
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"

# --- BULLETPROOF GOOGLE CREDENTIALS ---
# If a relative path is provided for GCP credentials (e.g. storage/keys/...),
# resolve it absolutely against the backend root so the Google SDK never crashes
# regardless of what folder the user runs the `python` command from.
_gcp_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if _gcp_creds:
    _gcp_creds_path = Path(_gcp_creds)
    if not _gcp_creds_path.is_absolute():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(BASE_DIR / _gcp_creds_path)

# --- STRICT ENTERPRISE PRIVACY ENFORCEMENT ---
# If Enterprise Vertex AI is mandated, we MUST crash immediately on boot if the
# JSON service account key is missing, rather than lazily failing API calls later.
VERTEX_AI_PROJECT = os.getenv("VERTEX_AI_PROJECT", "").strip()
if VERTEX_AI_PROJECT:
    _creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not _creds_path or not Path(_creds_path).exists():
        raise RuntimeError(
            f"\n\n[CRITICAL SECURITY ERROR] VERTEX_AI_PROJECT is enabled for Enterprise Privacy, "
            f"but the Service Account JSON key was not found at:\n{_creds_path}\n"
            f"Please check your GOOGLE_APPLICATION_CREDENTIALS path in .env or disable VERTEX_AI_PROJECT.\n"
        )

VERTEX_AI_LOCATION = os.getenv("VERTEX_AI_LOCATION", "asia-south1").strip()

FILES_DIR = STORAGE_DIR / "files"
EXCEL_FILE = STORAGE_DIR / "data" / "grievances.xlsx"
POLICY_DIR = STORAGE_DIR / "policies"
DEMO_POLICY_DIR = STORAGE_DIR / "demo_policies"
ATTACHMENTS_DIR = STORAGE_DIR / "attachments"
DATA_DIR = STORAGE_DIR / "data"

# Ensure required directories exist
for d in [FILES_DIR, DATA_DIR, POLICY_DIR, DEMO_POLICY_DIR, ATTACHMENTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- GOOGLE OAUTH CONFIGURATION ---
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback").strip()
OAUTH_ENCRYPTION_KEY = os.getenv("OAUTH_ENCRYPTION_KEY", "").strip()
OAUTH_TOKENS_DIR = DATA_DIR / "oauth_tokens"
OAUTH_TOKENS_DIR.mkdir(parents=True, exist_ok=True)

_cookie_secure_raw = os.getenv("OAUTH_COOKIE_SECURE", "false").strip().lower()
OAUTH_COOKIE_SECURE = (_cookie_secure_raw == "true") or (not IS_PRODUCTION) # False in dev for simplicity if not set

OAUTH_SUCCESS_REDIRECT_URL = os.getenv("OAUTH_SUCCESS_REDIRECT_URL", "").strip()
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]

# --- MICROSOFT OAUTH CONFIGURATION ---
MICROSOFT_OAUTH_CLIENT_ID = os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "").strip()
MICROSOFT_OAUTH_CLIENT_SECRET = os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "").strip()
MICROSOFT_OAUTH_REDIRECT_URI = os.getenv("MICROSOFT_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback").strip()
MICROSOFT_OAUTH_SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "offline_access",
]

# --- SECURITY & SESSIONS ---
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", OAUTH_ENCRYPTION_KEY).strip()
SEEDED_SUBJECT_PREFIX = "[AICOE-SEED]"

# Relax oauthlib strict scope checking to allow Google to inject 'openid' without crashing
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# --- DATABASE ---
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite").strip().lower()  # "sqlite" or "postgres"
DB_PATH = DATA_DIR / "grievances.db"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/grievance").strip()

# --- TASK QUEUE ---
TASK_QUEUE_TYPE = os.getenv("TASK_QUEUE_TYPE", "threadpool").strip().lower()  # "threadpool" or "celery"
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0").strip()
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0").strip()

# --- SYNC & PERFORMANCE ---
SYNC_ENABLED = os.getenv("SYNC_ENABLED", "true").lower() == "true"
GMAIL_CALLS_PER_MINUTE_LIMIT = int(os.getenv("GMAIL_CALLS_PER_MINUTE_LIMIT", "50"))
SYNC_JITTER_SECONDS = float(os.getenv("SYNC_JITTER_SECONDS", "60.0"))
SYNC_MAX_BACKOFF_SECONDS = float(os.getenv("SYNC_MAX_BACKOFF_SECONDS", "3600.0"))
GLOBAL_SYNC_INTERVAL_SECONDS = int(os.getenv("GLOBAL_SYNC_INTERVAL_SECONDS", "300"))
MANUAL_SYNC_COOLDOWN_SECONDS = int(os.getenv("MANUAL_SYNC_COOLDOWN_SECONDS", "120"))
FULL_SYNC_DAYS = int(os.getenv("FULL_SYNC_DAYS", "365"))

# --- CACHING & MEMORY ---
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
MAX_CACHE_ENTRIES = 20 if IS_PRODUCTION else 100
MAX_DF_ROWS = 5000 if IS_PRODUCTION else 20000
# Support both names for sync interval to match template
GLOBAL_SYNC_INTERVAL_SECONDS = int(os.getenv("GLOBAL_SYNC_INTERVAL_SECONDS", os.getenv("DYNAMIC_AUTO_REFRESH_SECONDS", "300")))

# --- AI & ANALYTICS ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", GOOGLE_API_KEY).strip()
CHATBOT_GEMINI_API_KEY = os.getenv("CHATBOT_GEMINI_API_KEY", GEMINI_API_KEY).strip()
PRIORITY_GEMINI_API_KEY = os.getenv("PRIORITY_GEMINI_API_KEY", GEMINI_API_KEY).strip()
PRIORITY_GOOGLE_API_KEY = os.getenv("PRIORITY_GOOGLE_API_KEY", PRIORITY_GEMINI_API_KEY).strip()

# VERTEX_AI_PROJECT and VERTEX_AI_LOCATION are handled during strict enforcement above.

AI_PREFER_LOCAL = os.getenv("AI_PREFER_LOCAL", "true").lower() == "true"
PRIMARY_LOCAL_MODEL = os.getenv("PRIMARY_LOCAL_MODEL", "llama3.2:3b").strip()

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


# --- REPLY GENERATION ---
REPLY_SENDER_NAME = os.getenv("REPLY_SENDER_NAME", "Grievance Support Desk").strip()

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
    "0": ["rti", "court order", "show cause", "show-cause", "chief secretary", "cabinet", "paper leakage", "accident", "emergency"],
    "1": ["cmo", "ragging", "anti-ragging", "anti ragging", "salary", "pension", "gratuity", "salary arrear", "fixation", "seniority", "suspension", "suspended", "disciplinary", "chargesheet", "misconduct", "fraud"],
    "2": ["exam", "semester", "result", "marksheet", "admit", "scholarship", "svmcm", "oasis", "fee", "tender", "procurement", "purchase", "accreditation", "naac", "nba", "nirf", "transfer", "posting", "deputation", "appointment", "matrix", "inspection", "audit", "confirmation", "cas", "career advancement", "jelet", "freeship", "cag"],
    "3": ["invitation", "induction", "workshop", "seminar", "conclave", "general", "query", "status", "acknowledge", "feedback", "newsletter", "advertisement", "ad"]
}

# --- RAG CONFIGURATION ---
INDEX_PATH = DATA_DIR / "rag_index.faiss"
CHUNKS_PATH = DATA_DIR / "policy_chunks.json"
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "15"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.35"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", RAG_MIN_SCORE))
RAG_FINAL_LIMIT = int(os.getenv("RAG_FINAL_LIMIT", "12"))
RAG_MAX_UNIQUE_SECTIONS = int(os.getenv("RAG_MAX_UNIQUE_SECTIONS", "3"))

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
