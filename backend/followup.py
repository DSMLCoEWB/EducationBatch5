import re
from rag.retriever import get_embedder

def get_model():
    """Use the shared singleton from retriever to save memory and time."""
    return get_embedder()

def has_explicit_reference(subject, content):
    """Check if email has explicit references to previous communication"""
    subject_lower = subject.lower().strip()
    content_lower = content.lower()
    
    # 1. High-confidence subject markers
    # We strip common prefixes like [AICOE-SEED] or [EXTERNAL] first
    clean_subject = re.sub(r'^\[[^\]]+\]\s*', '', subject_lower)
    if clean_subject.startswith(('re:', 'fwd:', 'aw:', 'wg:')):
        return True

    # 2. Body-based follow-up indicators (Strict word boundaries)
    followup_patterns = [
        r'\bregarding (?:my )?previous',
        r'\bas mentioned (?:in |at )?previous',
        r'\bin continuation (?:of|to)',
        r'\bfollowing up (?:on|regarding)',
        r'\bearlier mail',
        r'\bprevious mail',
        r'\bprevious email',
        r'\blast mail',
        r'\bagain sending',
        r'\bresending',
        r'\bresubmit',
    ]
    
    for pattern in followup_patterns:
        if re.search(pattern, content_lower):
            return True
    return False

def detect_followup(email, df, user_email=None):
    # -1. Admin Reply Check - If this is an outbound email sent by us, 
    # it is not a 'Follow-up' to the grievance, it is a 'Reply'.
    # EXCEPTION: If is_self_sent (sent to self), treat as a simulation (Fresh/Follow-up).
    is_sent = email.get("is_sent_by_me") or email.get("is_sent")
    is_in_inbox = email.get("is_inbox") or email.get("is_inbox") == 1

    if is_sent and not is_in_inbox:
        # THREAD AWARENESS: Distinguish between 'Reply' (to inquiry) and 'Fresh' (Admin started)
        tid = email.get("thread_id")
        if tid and df is not None and not df.empty:
            # Check if this thread has ANY citizen messages (is_sent=0)
            has_citizen_msg = df[(df["thread_id"] == tid) & (df["is_sent"] == 0)].shape[0] > 0
            if has_citizen_msg:
                return "Reply", None, 0
            else:
                return "Fresh", None, 0
        return "Reply", None, 0 # Default for outbound-only without context

    # 0. Gmail Threading - Only treat as follow-up if it's explicitly a response (Re:/Fwd:),
    # otherwise treat as a separate grievance even if Gmail threads them (common in self-tests).
    subject = email.get("subject", "")
    # Strip prefixes like [AICOE-SEED] for checking thread status
    clean_subject = re.sub(r'^\[[^\]]+\]\s*', '', subject.lower().strip())
    is_explicit_thread = clean_subject.startswith(('re:', 'fwd:', 'aw:', 'wg:'))
    
    eid = email.get("email_id")
    
    if email.get("thread_id") and not df.empty and is_explicit_thread:
        # Check if any other email in the cache has the same thread_id
        # EXCLUDE the current email itself if it happens to be in df (re-processing case)
        same_thread = df[(df["thread_id"] == email["thread_id"]) & (df["email_id"] != eid)]
        if not same_thread.empty:
            # Mark it as a follow-up to the most recent email in that thread
            parent = same_thread.iloc[-1]
            return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1

    # A. Manual Threading (Reliable Fallback) - Check parent_email_id
    if email.get("parent_email_id"):
        if not df.empty and email["parent_email_id"] in df["email_id"].values:
            parent = df[df["email_id"] == email["parent_email_id"]].iloc[0]
            return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1

    # B. Check for explicit references (Re:, Fwd:, etc.) ONLY
    # We no longer mark everything from same sender as follow-up to avoid self-test issues.
    content = email.get("content", "")
    
    if has_explicit_reference(subject, content) and not df.empty and email.get("sender"):
        # Filter by sender, and exclude current email
        same_sender_df = df[(df["sender"] == email["sender"]) & (df["email_id"] != eid)]
        if not same_sender_df.empty:
            # Find the most recent email from same sender as parent
            parent = same_sender_df.iloc[-1]
            return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1

    # Default: Fresh email
    return "Fresh", None, 0
