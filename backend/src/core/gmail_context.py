import threading
from typing import Dict, Any

# --- SINGLETONS ---
GMAIL_SERVICE_MAP: Dict[str, Any] = {} # user_email -> service object
GMAIL_SERVICE_LOCK = threading.Lock()
