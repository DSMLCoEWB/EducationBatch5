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
    """
    Refined Tagging Rules (Admin-Centric Perspective):
    1. Admin -> Others: Always 'Reply' (Administrative Action/Sent).
    2. Admin -> Self: 'Fresh' (1st) or 'Follow-up' (2nd+) -> Simulation for testing.
    3. Citizen -> Admin: 'Fresh' if 1st citizen msg in thread, else 'Follow-up'.
    """
    is_sent = email.get("is_sent_by_me") or email.get("is_sent")
    is_in_inbox = email.get("is_inbox") or email.get("is_inbox") == 1
    sender_email = (email.get("sender_email") or "").strip().lower()
    recipient_email = (email.get("recipient_email") or "").strip().lower()
    user_email_norm = user_email.strip().lower() if user_email else None
    
    # A true self-sent test is from you AND to you
    is_true_self_sent = user_email_norm and (sender_email == user_email_norm) and (recipient_email == user_email_norm)

    # RULE 1: All Outbound to others = "Reply" (Sent Action)
    if is_sent and not is_in_inbox and not is_true_self_sent:
        return "Reply", None, 0

    # Everything else is either a Citizen Inbound or a Self-Sent Test Simulation.
    tid = email.get("thread_id")
    eid = email.get("email_id")
    
    # If no thread context, it must be Fresh
    if not tid or df is None or df.empty:
        return "Fresh", None, 0

    # Find context in same thread
    same_thread = df[(df["thread_id"] == tid) & (df["email_id"] != eid)]
    if same_thread.empty:
        # Fallback to Manual Threading (parent_email_id)
        parent_id = email.get("parent_email_id")
        if parent_id and parent_id in df["email_id"].values:
            parent = df[df["email_id"] == parent_id].iloc[0]
            return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1
        return "Fresh", None, 0

    # --- REFINED CONTEXT LOGIC ---
    
    if is_true_self_sent:
        # SIMULATION MODE: Any previous messages in thread make it a follow-up
        parent = same_thread.iloc[-1]
        return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1

    # CITIZEN MODE: Check if NOT an admin-only thread
    # is_sent=0 means inbound from citizen. We only care if the citizen has spoken before.
    prev_citizen_msgs = same_thread[same_thread["is_sent"] == 0]
    
    if prev_citizen_msgs.empty:
        # Even if there are Admin messages (Notice sent by you), 
        # this is the FIRST message from the citizen -> Mark as Fresh (New Task).
        return "Fresh", None, 0
    else:
        # Citizen is following up on their own existing case
        parent = prev_citizen_msgs.iloc[-1]
        return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1
