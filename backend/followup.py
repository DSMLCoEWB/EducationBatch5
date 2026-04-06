import re
from rag.retriever import get_embedder

def get_model():
    """Use the shared singleton from retriever to save memory and time."""
    return get_embedder()

def has_explicit_reference(subject, content):
    """Check if email has explicit references to previous communication"""
    text = (subject + " " + content).lower()
    
    # Check for common follow-up indicators
    followup_patterns = [
        r'\bre:?\s',  # Re: or Re
        r'\bfwd:?\s',  # Fwd: or Fwd
        r'\bregarding previous',
        r'\bas mentioned',
        r'\bas per previous',
        r'\bin continuation',
        r'\bfollowing up',
        r'\bfollow-up',
        r'\bearlier mail',
        r'\bprevious mail',
        r'\bprevious email',
        r'\blast mail',
        r'\bagain sending',
        r'\bresending',
        r'\bresubmit',
    ]
    
    for pattern in followup_patterns:
        if re.search(pattern, text):
            return True
    return False

def detect_followup(email, df):
    # 0. Gmail Threading - Only treat as follow-up if it's explicitly a response (Re:/Fwd:),
    # otherwise treat as a separate grievance even if Gmail threads them (common in self-tests).
    subject = email.get("subject", "")
    is_explicit_thread = subject.lower().startswith(('re:', 'fwd:', 'aw:', 'wg:'))
    
    if email.get("thread_id") and not df.empty and is_explicit_thread:
        # Check if any other email in the cache has the same thread_id
        same_thread = df[df["thread_id"] == email["thread_id"]]
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
        same_sender_df = df[df["sender"] == email["sender"]]
        if not same_sender_df.empty:
            # Find the most recent email from same sender as parent
            parent = same_sender_df.iloc[-1]
            return "Follow-up", parent["email_id"], parent.get("followup_count", 0) + 1

    # Default: Fresh email
    return "Fresh", None, 0
