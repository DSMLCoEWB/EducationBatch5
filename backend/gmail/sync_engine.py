import time
import re
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.errors import HttpError

from config import (
    SYNC_ENABLED, SYNC_JITTER_SECONDS, MAX_DF_ROWS, 
    COLUMNS, MAX_CACHE_ENTRIES
)
from core.logging import get_logger
from gmail.client import get_gmail_api_service
from gmail.parser import parse_gmail_message_json
from db.repository import (
    get_user_sync_history, update_user_sync_history, 
    log_sync_audit, increment_sync_error, get_existing_gmail_ids,
    save_emails_batch
)
from cache.manager import (
    get_user_lock, dynamic_cache_df_by_user, dynamic_cache_at_by_user
)
from services.triage_service import (
    classify_grievance_heuristic, calculate_priority_heuristic,
    detect_followup, apply_thread_escalation
)

logger = get_logger("gmail.sync")

def sync_gmail_incremental(user_email: str) -> Dict[str, Any]:
    """
    Orchestrates the incremental synchronization of a user's Gmail account.
    Falls back to a guarded full sync if history IDs have expired.
    """
    if not SYNC_ENABLED:
        return {"status": "disabled", "sync_type": "NONE"}

    start_time = time.time()
    service = get_gmail_api_service(user_email)
    if not service:
        return {"status": "failed", "error": "Could not initialize Gmail service"}

    history_data = get_user_sync_history(user_email)
    last_history_id = history_data.get("last_history_id") if history_data else None

    # NO HISTORY ID -> Trigger initial full sync
    if not last_history_id:
        logger.info(f"🆕 [Sync] No history found for {user_email}. Triggering initial full sync.")
        added, next_id = _guarded_full_sync(service, user_email)
        update_user_sync_history(user_email, next_id)
        return {"status": "success", "sync_type": "INITIAL_FULL", "added": added}

    try:
        # 1. Fetch History Updates
        history_response = service.users().history().list(
            userId="me", startHistoryId=last_history_id, historyTypes=["messageAdded", "labelAdded", "labelRemoved"]
        ).execute()
        
        new_history_id = history_response.get("historyId")
        changes = history_response.get("history", [])
        
        new_messages = []
        deleted_count = 0
        
        # 2. Extract Message IDs from History
        mids_to_fetch = set()
        for h in changes:
            for added in h.get("messagesAdded", []):
                mids_to_fetch.add(added["message"]["id"])
            for label in h.get("labelAdded", []):
                # We specifically look for things moving into INBOX or TRASH
                label_ids = label.get("labelIds", [])
                if "INBOX" in label_ids or "TRASH" in label_ids:
                    mids_to_fetch.add(label["message"]["id"])

        # 2b. Extract Label State Changes (Mirroring deletes/restores)
        from db.repository import update_email_labels_locally
        for h_record in changes:
            # Handle restorations (Trash removed)
            for removed in h_record.get("labelsRemoved", []):
                if "TRASH" in removed.get("labelIds", []):
                    update_email_labels_locally(user_email, removed["message"]["id"], is_trashed=False)
            
            # Handle deletions (Trash added)
            for added in h_record.get("labelsAdded", []):
                if "TRASH" in added.get("labelIds", []):
                    update_email_labels_locally(user_email, added["message"]["id"], is_trashed=True)

        # 3. Process New/Updated Messages
        if mids_to_fetch:
            # Filter out already known IDs
            existing_ids = get_existing_gmail_ids(user_email)
            to_fetch = [mid for mid in mids_to_fetch if mid not in existing_ids]
            
            # Context for thread detection
            existing_df = build_dynamic_dataframe(user_email)
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(_process_single_message_optimized, user_email, mid, service, existing_df) for mid in to_fetch]
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        new_messages.append(res)

        if new_messages:
            save_emails_batch(user_email, new_messages)

        # 4. Success State Update
        update_user_sync_history(user_email, new_history_id)
        duration_ms = int((time.time() - start_time) * 1000)
        log_sync_audit(user_email, "INCREMENTAL", "SUCCESS", duration_ms, added=len(new_messages))
        
        return {
            "status": "success",
            "sync_type": "INCREMENTAL",
            "added": len(new_messages),
            "new_history_id": new_history_id
        }

    except HttpError as e:
        if e.resp.status in [404, 410]:
            logger.warning(f"⚠️ [Sync] History expired for {user_email}. Performing recovery full sync.")
            added, next_id = _guarded_full_sync(service, user_email)
            update_user_sync_history(user_email, next_id)
            return {"status": "success", "sync_type": "RECOVERY_FULL", "added": added}
        
        increment_sync_error(user_email)
        logger.error(f"❌ [Sync] Incremental sync failed for {user_email}: {e}")
        return {"status": "failed", "error": str(e)}

def _guarded_full_sync(service: Any, user_email: str) -> Tuple[int, str]:
    """Performs a limited-scope full sync to populate the database safely."""
    query = "newer_than:14d"
    results = service.users().messages().list(userId="me", q=query, maxResults=500).execute()
    messages = results.get("messages", [])
    
    existing_ids = get_existing_gmail_ids(user_email)
    new_ids = [m["id"] for m in messages if m["id"] not in existing_ids]
    existing_df = build_dynamic_dataframe(user_email)
    
    ingested = []
    # Use pool for speed but keep concurrency low to stay below user quotas
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_process_single_message_optimized, user_email, mid, service, existing_df) for mid in new_ids]
        for f in as_completed(futures):
            res = f.result()
            if res:
                ingested.append(res)
                
    if ingested:
        save_emails_batch(user_email, ingested)
        
    profile = service.users().getProfile(userId="me").execute()
    return len(ingested), profile.get("historyId")

def _process_single_message_optimized(user_email: str, msg_id: str, service: Optional[Any] = None, context_df: Optional[pd.DataFrame] = None) -> Optional[Dict[str, Any]]:
    """
    SINGLE-FETCH STRATEGY: Fetches 'full' JSON which contains metadata, headers, AND part structure.
    Parses body and attachment metadata without needing a second 'raw' call.
    """
    try:
        svc = service or get_gmail_api_service(user_email)
        if not svc:
            return None
            
        # 1. Fetch Full JSON (Contains labels, headers, and body parts)
        # This is the "One Fetch Strategy"
        msg_json = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        
        # 2. Use the JSON Parser
        email_data = parse_gmail_message_json(msg_json)
        
        # 3. Add Folder Flags (Gmail Specific)
        label_ids = msg_json.get("labelIds", [])
        email_data["is_inbox"] = 1 if "INBOX" in label_ids else 0
        email_data["is_sent"] = 1 if "SENT" in label_ids else 0
        email_data["is_trashed"] = 1 if "TRASH" in label_ids else 0
        
        # 4. Instant Heuristic Triage (Category & Priority)
        content = email_data.get("content", "")
        subject = email_data.get("subject", "")
        
        email_data["category"] = classify_grievance_heuristic(content, subject)
        email_data["priority"] = calculate_priority_heuristic(content, subject)
        
        # 5. Thread Awareness (Instant logic)
        mail_type, parent_id, f_count = detect_followup(email_data, context_df, user_email)
        
        email_data["mail_type"] = mail_type
        email_data["parent_email_id"] = parent_id
        email_data["followup_count"] = f_count
        
        # 6. Priority Escalation (If it's a follow-up, bump it)
        if mail_type == "Follow-up":
            raw_prio = email_data["priority"]
            email_data["priority"] = apply_thread_escalation(raw_prio, f_count)
        
        # 7. Map ID to our internal scheme
        # Note: 'id' from parser already standardized
        return email_data

    except Exception as e:
        logger.error(f"❌ Error processing message {msg_id}: {e}")
        return None

def build_dynamic_dataframe(user_email: str) -> pd.DataFrame:
    """
    Interface for the routes/cache to build a fresh DataFrame from DB.
    Also handles flag reconciliation for moved/deleted items.
    """
    # This will be refined as we move reconcile_email_flags to db/repository
    from db.repository import get_emails_from_db
    emails = get_emails_from_db(user_email, category='all')
    return pd.DataFrame(emails)
