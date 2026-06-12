import time
import os
import requests
import pandas as pd
from typing import Dict, Any, Optional, Tuple, List

from config import SYNC_ENABLED
from core.logging import get_logger
from core.auth import get_valid_microsoft_token
from db.repository import (
    get_user_sync_history, update_user_sync_history, 
    log_sync_audit, increment_sync_error, get_existing_gmail_ids,
    save_emails_batch, get_emails_from_db, reconcile_user_thread_tags,
    ensure_user_categories, permanently_delete_email_locally,
    auto_purge_stale_trash
)
from services.triage_service import (
    classify_grievance_heuristic, calculate_priority_heuristic,
    detect_followup, apply_thread_escalation
)

logger = get_logger("microsoft.sync")

def get_ms_headers(user_email: str) -> Optional[Dict[str, str]]:
    access_token = get_valid_microsoft_token(user_email)
    if not access_token:
        return None
    return {"Authorization": f"Bearer {access_token}"}

def build_dynamic_dataframe(user_email: str) -> pd.DataFrame:
    emails = get_emails_from_db(user_email, category='all')
    return pd.DataFrame(emails)

def parse_microsoft_message(msg: Dict[str, Any], user_email: str, context_df: pd.DataFrame, folder_type: str = "inbox", headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    # We map MS properties to our 'gmail' DB schema
    
    # 1. Metadata extraction
    msg_id = msg.get("id")
    # MS doesn't have threadId like Google natively, but has conversationId
    thread_id = msg.get("conversationId", msg_id)
    subject = msg.get("subject", "No Subject")
    import re
    body_dict = msg.get("body", {})
    body_content = body_dict.get("content", "")
    content_type = body_dict.get("contentType", "").lower()
    
    if content_type == "html":
        html_content = body_content
        # Strip HTML tags to create plain text for search and AI triage
        content = re.sub(r'<[^>]+>', ' ', html_content)
        content = re.sub(r'\s+', ' ', content).strip()
    else:
        html_content = ""
        content = body_content
        
    if not content:
        content = msg.get("bodyPreview", "")
    
    sender_dict = msg.get("sender", {}).get("emailAddress", {})
    sender_name = sender_dict.get("name", "")
    sender_email = sender_dict.get("address", "")
    sender_str = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    
    # Received date
    date_str = msg.get("receivedDateTime")
    
    # Extract recipients
    def parse_recipients(recipients_list):
        if not recipients_list:
            return ""
        parsed = []
        for r in recipients_list:
            addr = r.get("emailAddress", {})
            name = addr.get("name", "")
            email = addr.get("address", "")
            if name and email and name != email:
                parsed.append(f"{name} <{email}>")
            elif email:
                parsed.append(email)
        return ", ".join(parsed)

    to_str = parse_recipients(msg.get("toRecipients", []))
    cc_str = parse_recipients(msg.get("ccRecipients", []))
    bcc_str = parse_recipients(msg.get("bccRecipients", []))

    # 2. Schema mapping
    email_data = {
        "email_id": msg_id,
        "gmail_id": msg_id,  # Reuse gmail_id column for MS ID
        "thread_id": thread_id,
        "sender": sender_str,
        "sender_email": sender_email,
        "recipient_email": user_email,
        "to": to_str,
        "cc": cc_str,
        "bcc": bcc_str,
        "subject": subject,
        "content": content,
        "date": date_str,
        "has_attachment": msg.get("hasAttachments", False),
        "attachments": [],
        "html_content": html_content,
        "is_demo": False,
        "is_inbox": 1 if folder_type == "inbox" else 0,
        "is_trashed": 1 if folder_type == "deleteditems" else 0,
        "is_sent": 1 if folder_type == "sentitems" else 0,
        "replied": False
    }
    
    # 3. Triage
    email_data["category"] = classify_grievance_heuristic(content, subject, user_email=user_email)
    email_data["priority"] = calculate_priority_heuristic(content, subject, user_email=user_email)
    
    # 4. Thread logic
    mail_type, parent_id, f_count = detect_followup(email_data, context_df, user_email)
    email_data["mail_type"] = mail_type
    email_data["parent_email_id"] = parent_id
    email_data["followup_count"] = f_count
    
    if mail_type == "Follow-up":
        email_data["priority"] = apply_thread_escalation(email_data["priority"], f_count)
        
    # 5. Download Attachments & Remap Inline Images
    # MS Graph sometimes returns hasAttachments=False for inline images, so we also check the HTML body for 'cid:'
    needs_attachment_fetch = email_data.get("has_attachment") or ('cid:' in html_content.lower())
    if needs_attachment_fetch and headers:
        downloaded_atts, cid_map = _fetch_and_save_ms_attachments(headers, msg_id, user_email)
        if downloaded_atts:
            email_data["attachments"] = downloaded_atts
            email_data["has_attachment"] = True
            
        # Rewrite HTML CIDs for inline images
        if email_data.get("html_content") and cid_map:
            email_data["html_content"] = _rewrite_html_cids(email_data["html_content"], cid_map)
            
    return email_data

def sync_microsoft_incremental(user_email: str) -> Dict[str, Any]:
    if not SYNC_ENABLED:
        return {"status": "disabled", "sync_type": "NONE"}

    ensure_user_categories(user_email)
    start_time = time.time()
    
    headers = get_ms_headers(user_email)
    if not headers:
        return {"status": "failed", "error": "No valid MS tokens"}
        
    history_data = get_user_sync_history(user_email)
    
    # Track delta links for each folder
    delta_links = {
        "inbox": history_data.get("microsoft_delta_link") if history_data else None,
        "sentitems": history_data.get("microsoft_delta_link_sent") if history_data else None,
        "deleteditems": history_data.get("microsoft_delta_link_trash") if history_data else None
    }
    
    new_messages = []
    deleted_count = 0
    
    try:
        existing_df = build_dynamic_dataframe(user_email)
        existing_ids = get_existing_gmail_ids(user_email)
        
        folders_to_sync = ["inbox", "sentitems", "deleteditems"]
        
        from datetime import datetime, timedelta
        from config import FULL_SYNC_DAYS
        cutoff_date = (datetime.utcnow() - timedelta(days=FULL_SYNC_DAYS)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        for folder in folders_to_sync:
            is_initial_sync = (delta_links[folder] is None)
            
            if is_initial_sync:
                # 1. Grab the latest delta token FIRST to ensure no missed emails
                delta_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages/delta?$deltaToken=latest"
                res = requests.get(delta_url, headers=headers, timeout=(5, 30))
                res.raise_for_status()
                delta_data = res.json()
                delta_links[folder] = delta_data.get("@odata.deltaLink")
                
                # 2. Fetch historical bounded data
                time_filter_field = "sentDateTime" if folder == "sentitems" else "receivedDateTime"
                hist_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages?$filter={time_filter_field} ge {cutoff_date}&$top=50"
                while hist_url:
                    res = requests.get(hist_url, headers=headers, timeout=(5, 30))
                    res.raise_for_status()
                    data = res.json()
                    for msg in data.get("value", []):
                        if msg["id"] not in existing_ids:
                            parsed = parse_microsoft_message(msg, user_email, existing_df, folder, headers)
                            new_messages.append(parsed)
                    hist_url = data.get("@odata.nextLink")
            else:
                # Standard Incremental Sync
                url = delta_links[folder]
                while url:
                    res = requests.get(url, headers=headers, timeout=(5, 30))
                    res.raise_for_status()
                    data = res.json()
                    
                    for msg in data.get("value", []):
                        if "@removed" in msg:
                            permanently_delete_email_locally(user_email, msg["id"])
                            deleted_count += 1
                        else:
                            if msg["id"] not in existing_ids:
                                parsed = parse_microsoft_message(msg, user_email, existing_df, folder, headers)
                                new_messages.append(parsed)
                    
                    if "@odata.nextLink" in data:
                        url = data["@odata.nextLink"]
                    elif "@odata.deltaLink" in data:
                        delta_links[folder] = data["@odata.deltaLink"]
                        url = None
                    else:
                        break
                    
        if new_messages:
            save_emails_batch(user_email, new_messages)
            reconcile_user_thread_tags(user_email)
            from core.notifier import SSE_NOTIFIER
            SSE_NOTIFIER.notify(user_email)
            
        auto_purge_stale_trash(user_email)
        
        update_user_sync_history(
            user_email, 
            microsoft_delta_link=delta_links["inbox"],
            microsoft_delta_link_sent=delta_links["sentitems"],
            microsoft_delta_link_trash=delta_links["deleteditems"]
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        log_sync_audit(user_email, "INCREMENTAL", "SUCCESS", duration_ms, added=len(new_messages))
        
        return {
            "status": "success",
            "sync_type": "INCREMENTAL",
            "added": len(new_messages),
            "deleted": deleted_count
        }
    except Exception as e:
        increment_sync_error(user_email)
        logger.error(f"❌ [Sync] MS sync failed for {user_email}: {e}")
        return {"status": "failed", "error": str(e)}

def _fetch_and_save_ms_attachments(headers: Dict[str, str], msg_id: str, user_email: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Downloads attachments from MS Graph and saves them locally."""
    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
        res = requests.get(url, headers=headers, timeout=(5, 30))
        res.raise_for_status()
        attachments = res.json().get("value", [])
        
        downloaded_atts = []
        cid_map = {}
        
        if not attachments:
            return downloaded_atts, cid_map
            
        import base64, hashlib, re
        from config import ATTACHMENTS_DIR
        from utils.email_utils import normalize_email_address
        
        slug = re.sub(r'[^a-z0-9]', '_', normalize_email_address(user_email).lower())
        user_att_dir = os.path.join(ATTACHMENTS_DIR, slug)
        os.makedirs(user_att_dir, exist_ok=True)
        
        for att in attachments:
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
                
            filename = att.get("name", "unnamed_attachment")
            size = att.get("size", 0)
            
            limit_bytes = 10 * 1024 * 1024
            if size > limit_bytes:
                logger.warning(f"⚠️ [Sync] Skipping large attachment for {user_email}: {filename} ({size} bytes).")
                continue
                
            content_bytes = att.get("contentBytes", "")
            if not content_bytes:
                continue
                
            payload = base64.b64decode(content_bytes)
            file_hash = hashlib.md5(payload).hexdigest()[:8]
            safe_fname = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
            unique_fname = f"{file_hash}_{safe_fname}"
            path = os.path.join(user_att_dir, unique_fname)
            
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(payload)
                    
            att_meta = {
                "attachment_id": att.get("id"),
                "filename": filename,
                "mime_type": att.get("contentType", ""),
                "size": size,
                "local_path": path
            }
            
            content_id = att.get("contentId")
            if content_id:
                # contentId may be enclosed in <> e.g. <image001.png@01D...>
                clean_cid = content_id.strip("<>")
                att_meta["content_id"] = clean_cid
                cid_map[clean_cid] = unique_fname
                
            downloaded_atts.append(att_meta)
            
        return downloaded_atts, cid_map
    except Exception as e:
        logger.error(f"❌ [Sync] Failed to download MS attachments for {msg_id}: {e}")
        return [], {}

def _rewrite_html_cids(html: str, cid_map: Dict[str, str]) -> str:
    """Replaces src='cid:...' references in HTML with local backend download URLs."""
    if not html: return html
    import re
    for cid, unique_filename in cid_map.items():
        escaped_cid = re.escape(cid)
        pattern = rf'src=["\']cid:{escaped_cid}["\']'
        replacement = f'src="__API_BASE_URL__/emails/download/attachment/{unique_filename}"'
        html = re.sub(pattern, replacement, html)
    return html
