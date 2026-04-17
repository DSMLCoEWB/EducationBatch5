import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import pandas as pd

from config import (
    CATEGORIES, PRIORITY_KEYWORDS
)
from core.logging import get_logger
from priority_llm import get_batch_triage, apply_thread_escalation

logger = get_logger("services.triage")

# --- HEURISTIC ENGINE (Instant) ---

def classify_grievance_heuristic(text: str, subject: str = "", attachment_content: str = "") -> str:
    """Keyword-based classification for instant categorization in the sync path."""
    if not text and not subject and not attachment_content:
        return "Miscellaneous"

    clean_text = re.sub(r'<[^>]+>', ' ', str(text or ''))
    composite_text = f"{subject} {subject}\n{clean_text}\n{attachment_content or ''}".lower()
    text_normalized = re.sub(r'\s+', ' ', composite_text).strip()
    
    category_scores = defaultdict(float)
    for category, keywords in CATEGORIES.items():
        score = 0
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            matches = len(re.findall(pattern, text_normalized))
            score += matches * (2 if ' ' in keyword else 1)
        category_scores[category] = float(score)

    if category_scores:
        max_score = max(category_scores.values())
        if max_score > 0:
            for category in CATEGORIES: # Preservation of insertion order for ties
                if category_scores[category] == max_score:
                    return category

    return "Miscellaneous"

def calculate_priority_heuristic(content: str, subject: str) -> int:
    """Assigns 0-6 priority level based on keyword weightings."""
    text = f"{subject} {content}".lower()
    
    # Check for highest levels first
    for level_str, keywords in PRIORITY_KEYWORDS.items():
        level = int(level_str)
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                return level
                
    return 6 # Default misc/low

# --- THREAD AWARENESS ---

def detect_followup(email: Dict[str, Any], df: Optional[pd.DataFrame], user_email: Optional[str] = None) -> Tuple[str, Optional[str], int]:
    """
    Determines if an email is Fresh, a Follow-up, or a Reply based on thread history.
    """
    is_sent = email.get("is_sent_by_me") or email.get("is_sent")
    is_in_inbox = email.get("is_inbox")
    sender_email = (email.get("sender_email") or "").strip().lower()
    recipient_email = (email.get("recipient_email") or "").strip().lower()
    user_email_norm = user_email.strip().lower() if user_email else None
    
    # Logic for Outbound
    if is_sent and not is_in_inbox:
        if user_email_norm and recipient_email != user_email_norm:
             return "Reply", None, 0

    tid = email.get("thread_id")
    eid = email.get("email_id")
    
    if not tid or df is None or df.empty:
        return "Fresh", None, 0

    same_thread = df[(df["thread_id"] == tid) & (df["email_id"] != eid)]
    if same_thread.empty:
        return "Fresh", None, 0

    # Thread found: Mark as follow-up and increment count
    parent = same_thread.iloc[-1]
    f_count = int(parent.get("followup_count", 0)) + 1
    return "Follow-up", str(parent.get("email_id")), f_count

# --- AI REFINEMENT (Delegated) ---

def get_batch_triage_ai(emails: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Delegates to priority_llm.py for official batch processing and rate-limiting.
    """
    # Simply reuse the well-tested logic from priority_llm
    return get_batch_triage(emails)
