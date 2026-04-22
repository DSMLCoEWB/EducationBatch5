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

from utils.email_utils import normalize_email_address

def detect_followup(email: Dict[str, Any], df: Optional[pd.DataFrame], user_email: Optional[str] = None) -> Tuple[str, Optional[str], int]:
    """
    Determines if an email is Fresh, a Follow-up, or a Reply based on interaction history.
    New Model (Interaction-First): 
    - The first external inbound in any thread is always 'Fresh'.
    - Proactive outbound before any inbound is 'Action'.
    """
    is_sent = bool(email.get("is_sent_by_me") or email.get("is_sent"))
    
    user_norm = normalize_email_address(user_email)
    sender_norm = normalize_email_address(email.get("sender_email") or email.get("sender"))
    recipient_norm = normalize_email_address(email.get("recipient_email"))

    tid = email.get("thread_id")
    eid = email.get("email_id")
    
    # 1. STANDALONE CASE
    if not tid or df is None or df.empty:
        if is_sent and recipient_norm != user_norm:
            return "Action", None, 0
        return "Fresh", None, 0

    # 2. THREAD CASE: Analyze interaction history
    same_thread = df[(df["thread_id"] == tid) & (df["email_id"] != eid)]
    if same_thread.empty:
        if is_sent and recipient_norm != user_norm:
            return "Action", None, 0
        return "Fresh", None, 0

    # Identify if there were previous external inbounds in this thread
    # (Matches current inbound/outbound logic: not is_sent and sender != me)
    # Note: Normalize df sender_email for comparison
    df_is_sent = same_thread['is_sent'].astype(bool)
    previous_external_inbounds = same_thread[~df_is_sent]
    
    inbound_count = len(previous_external_inbounds)

    if is_sent:
        # OUTBOUND LOGIC
        if recipient_norm == user_norm:
            if same_thread.empty:
                return "Fresh", None, 0
            return "Follow-up", str(same_thread.iloc[-1].get("email_id")), int(same_thread.iloc[-1].get("followup_count", 0)) + 1
        
        if inbound_count > 0:
            return "Reply", str(same_thread.iloc[-1].get("email_id")), int(same_thread.iloc[-1].get("followup_count", 0)) + 1
        else:
            return "Action", str(same_thread.iloc[-1].get("email_id")), int(same_thread.iloc[-1].get("followup_count", 0)) + 1
    else:
        # INBOUND LOGIC
        if inbound_count == 0:
            # First time the external party has replied!
            return "Fresh", str(same_thread.iloc[-1].get("email_id")), 0
        else:
            # Subsequent inbounds
            f_count = int(same_thread.iloc[-1].get("followup_count", 0)) + 1
            return "Follow-up", str(same_thread.iloc[-1].get("email_id")), f_count

# --- AI REFINEMENT (Delegated) ---

def get_batch_triage_ai(emails: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Delegates to priority_llm.py for official batch processing and rate-limiting.
    """
    # Simply reuse the well-tested logic from priority_llm
    return get_batch_triage(emails)
