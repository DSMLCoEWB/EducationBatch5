from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os
import asyncio
from datetime import datetime

from core.dependencies import get_authenticated_user
from db.repository import (
    get_db_conn, update_sync_interval, get_user_sync_history,
    mark_as_trashed, get_emails_from_db, get_refinement_stats,
    get_categories_from_db, get_dashboard_stats, get_thread_from_db,
    permanently_delete_email_locally, toggle_resolution_status
)
from gmail.sync_engine import sync_gmail_incremental

from gmail.client import get_gmail_api_service, get_user_display_name
from core.notifier import SSE_NOTIFIER
from core.coordination import trigger_intelligence_suite, run_background_sync_loop
from core.context import worker_manager
from config import FILES_DIR, MANUAL_SYNC_COOLDOWN_SECONDS

router = APIRouter(prefix="/emails", tags=["Emails"])

@router.post("/{email_id}/resolve")
def resolve_email(
    email_id: str, 
    resolved: bool = Query(True),
    user_email: str = Depends(get_authenticated_user)
):
    """Manually marks a grievance thread as resolved/unresolved."""
    toggle_resolution_status(user_email, email_id, resolved)
    SSE_NOTIFIER.notify(user_email)
    return {"status": "success", "resolved": resolved}

@router.get("/")
def list_emails(
    category: str = Query(..., description="Email category or 'all'"),
    is_demo: Optional[bool] = Query(None),
    user_email: str = Depends(get_authenticated_user)
):
    """Fetches emails from the repository with optional filtering."""
    try:
        emails = get_emails_from_db(user_email, category=category, is_demo=is_demo)
        return emails
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, user_email: str = Depends(get_authenticated_user)):
    """Fetches all emails in a specific conversation thread."""
    try:
        threads = get_thread_from_db(user_email, thread_id)
        if not threads:
             raise HTTPException(status_code=404, detail="Thread not found")
        return threads
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{email_id}/trash")
def trash_email(email_id: str, user_email: str = Depends(get_authenticated_user)):
    """Moves an email to trash locally and on Gmail."""
    service = get_gmail_api_service(user_email)
    mark_as_trashed(user_email, email_id, True)
    
    # Background sync with Gmail
    if service:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT gmail_id FROM emails WHERE id = ?", (email_id,))
            row = cursor.fetchone()
            if row and row[0]:
                gmail_id = row[0]
                try:
                    service.users().messages().trash(userId="me", id=gmail_id).execute()
                    # Notify UI to refresh local view
                    SSE_NOTIFIER.notify(user_email)
                except Exception as e:
                    # If it's already gone from Gmail, purge it locally too
                    if hasattr(e, 'resp') and e.resp.status == 404:
                        permanently_delete_email_locally(user_email, gmail_id)
                        SSE_NOTIFIER.notify(user_email)
                    pass
    return {"status": "trashed"}

@router.post("/{email_id}/untrash")
def untrash_email(email_id: str, user_email: str = Depends(get_authenticated_user)):
    """Restores an email from trash."""
    service = get_gmail_api_service(user_email)
    mark_as_trashed(user_email, email_id, False)
    
    if service:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT gmail_id FROM emails WHERE id = ?", (email_id,))
            row = cursor.fetchone()
            if row and row[0]:
                gmail_id = row[0]
                try:
                    service.users().messages().untrash(userId="me", id=gmail_id).execute()
                    # Notify UI to refresh local view
                    SSE_NOTIFIER.notify(user_email)
                except Exception as e:
                    # If it's already gone from Gmail, purge it locally too
                    if hasattr(e, 'resp') and e.resp.status == 404:
                        permanently_delete_email_locally(user_email, gmail_id)
                        SSE_NOTIFIER.notify(user_email)
                    pass
    return {"status": "restored"}

@router.post("/sync")
def trigger_sync_manual(user_email: str = Depends(get_authenticated_user)):
    """
    Manual sync trigger with a strict 120s cooldown (Anti-Bot Safeguard).
    """
    history = get_user_sync_history(user_email)
    if history and history.get("last_sync_completed"):
        last_sync = datetime.fromisoformat(history["last_sync_completed"])
        elapsed = (datetime.now() - last_sync).total_seconds()
        if elapsed < MANUAL_SYNC_COOLDOWN_SECONDS:
             raise HTTPException(
                 status_code=429, 
                 detail=f"Cooldown active. Please wait {int(MANUAL_SYNC_COOLDOWN_SECONDS - elapsed)}s for stealth protection."
             )

    if not worker_manager.is_sync_running(user_email):
        worker_manager.start_sync_worker(user_email, run_background_sync_loop)
    
    # Immediate incremental sync in foreground for responsiveness
    SSE_NOTIFIER.notify(user_email, "sync_started")
    sync_gmail_incremental(user_email)
    
    trigger_intelligence_suite(user_email)
    # Notify UI that sync is complete
    SSE_NOTIFIER.notify(user_email)
    return {"status": "sync_complete"}

@router.post("/settings/sync-interval")
def update_sync_settings(
    interval: int = Query(..., ge=180, le=14400), # 3 min to 4 hours
    user_email: str = Depends(get_authenticated_user)
):
    """Updates the user's background stealth-sync interval (Single-Clock knob)."""
    update_sync_interval(user_email, interval)
    return {"status": "success", "new_interval": interval}

@router.get("/settings/sync-interval")
def get_sync_settings(user_email: str = Depends(get_authenticated_user)):
    """Retrieves current stealth-sync settings."""
    history = get_user_sync_history(user_email)
    interval = history.get("sync_interval_seconds", 300) if history else 300
    return {"sync_interval_seconds": interval}

@router.get("/sync-status")
def get_sync_status(user_email: str = Depends(get_authenticated_user)):
    """Passive sync status check for dashboard initialization."""
    is_running = worker_manager.is_sync_running(user_email)
    return {"syncing": is_running}


@router.get("/stats/refinement")
def refinement_stats(user_email: str = Depends(get_authenticated_user)):
    """Returns AI refinement coverage statistics."""
    return get_refinement_stats(user_email)

@router.get("/categories")
def list_categories(user_email: str = Depends(get_authenticated_user)):
    """Returns grievance categories and their counts."""
    return get_categories_from_db(user_email)

@router.get("/dashboard")
def get_dashboard(user_email: str = Depends(get_authenticated_user)):
    """Returns high-level summary counts."""
    return get_dashboard_stats(user_email)

class ComposeRequest(BaseModel):
    to_email: str
    subject: str
    body: str

@router.post("/compose")
def compose_email(payload: ComposeRequest, user_email: str = Depends(get_authenticated_user)):
    """Composes and sends a new standalone Gmail message."""
    from email.utils import formataddr
    import base64
    from email.mime.text import MIMEText
    
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    display_name, official_email = get_user_display_name(user_email)
    message = MIMEText(payload.body)
    message['to'] = payload.to_email
    if display_name:
        message['From'] = formataddr((display_name, official_email))
    message['subject'] = payload.subject
    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        sent_msg = service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
        
        # Force immediate incremental sync to persist the sent email to SQLite
        from gmail.sync_engine import sync_gmail_incremental
        sync_gmail_incremental(user_email)
        
        # Notify UI to refresh dashboard as a 'Sent' item was created
        SSE_NOTIFIER.notify(user_email)
        return {"success": True, "id": sent_msg['id'], "status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-reply")
def send_reply(
    payload: Dict[str, Any],
    user_email: str = Depends(get_authenticated_user)
):
    """Sends a reply via Gmail and marks the local thread as replied."""
    from email.utils import formataddr
    import base64
    from email.mime.text import MIMEText
    
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    display_name, official_email = get_user_display_name(user_email)
    to_email = payload.get("to_email")
    subject = payload.get("original_subject", "")
    body = payload.get("reply_text", "")
    email_id = payload.get("email_id")
    
    # 1. Thread Reconciliation: Look up actual thread data from DB
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT gmail_id, thread_id FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        row = cursor.fetchone()
        
    actual_gmail_id = row[0] if row else None
    actual_thread_id = row[1] if row else None
 
    # 2. Construct MIME message
    message = MIMEText(body)
    message['to'] = to_email
    if display_name:
        message['From'] = formataddr((display_name, official_email))
    message['subject'] = subject if (subject.startswith("Re:") or subject.startswith("Fwd:")) else f"Re: {subject}"
    
    # Standard Threading Headers
    if actual_gmail_id:
        message['In-Reply-To'] = actual_gmail_id
        message['References'] = actual_gmail_id
        
    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        service.users().messages().send(
            userId='me', 
            body={'raw': raw_msg, 'threadId': actual_thread_id} if actual_thread_id else {'raw': raw_msg}
        ).execute()
        
        # Force immediate incremental sync to persist the reply to SQLite
        from gmail.sync_engine import sync_gmail_incremental
        sync_gmail_incremental(user_email)
        
        # Notify UI to refresh
        SSE_NOTIFIER.notify(user_email)
        return {"success": True, "message": "Reply sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/events")
async def email_events(request: Request, user_email: str = Depends(get_authenticated_user)):
    """
    Server-Sent Events (SSE) endpoint for real-time dashboard updates.
    Provides a persistent, passive stream for 'sync_complete' signals.
    """
    from fastapi.responses import StreamingResponse
    
    async def event_generator():
        queue = SSE_NOTIFIER.subscribe(user_email)
        try:
            # Initial heartbeat to establish connection
            yield f"data: {json.dumps({'event': 'connected'})}\n\n"
            
            while True:
                # Wait for broadcast from background workers
                event_type = await queue.get()
                yield f"data: {json.dumps({'event': event_type})}\n\n"
                queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            SSE_NOTIFIER.unsubscribe(user_email, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no" # Essential for proxy (HF Spaces)
        }
    )

@router.get("/colleges")
def list_colleges(user_email: str = Depends(get_authenticated_user)):
    """
    Returns distinct institute names dynamically extracted from AI-processed emails.
    Self-growing: no hardcoded file needed — the list expands as new grievances are processed.
    """
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT institute_name 
            FROM emails 
            WHERE user_email = ? 
              AND institute_name IS NOT NULL 
              AND institute_name != ''
              AND institute_name != 'Individual / Public'
            ORDER BY institute_name
        """, (user_email,))
        names = [row[0] for row in cursor.fetchall()]
    return {"colleges": names}

@router.get("/download/{eml_filename}")
def download_eml(eml_filename: str):
    """Provides original .eml files for specialized workflows."""
    path = os.path.join(FILES_DIR, eml_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="message/rfc822")

@router.get("/download/attachment/{filename}")
def download_attachment(
    filename: str,
    user_email: str = Depends(get_authenticated_user)
):
    """Provides direct access to stored email attachments and inline images with user isolation."""
    from config import ATTACHMENTS_DIR
    import mimetypes
    import re
    from utils.email_utils import normalize_email_address
    
    # Path Traversal Protection & User Isolation
    safe_filename = os.path.basename(filename)
    slug = re.sub(r'[^a-z0-9]', '_', normalize_email_address(user_email).lower())
    path = os.path.join(ATTACHMENTS_DIR, slug, safe_filename)
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Attachment not found or access denied")
        
    mime_type, _ = mimetypes.guess_type(path)
    return FileResponse(
        path, 
        media_type=mime_type or "application/octet-stream",
        filename=safe_filename.split('_', 1)[-1] if '_' in safe_filename else safe_filename
    )

@router.post("/reprocess-attachment")
def reprocess_attachment(
    email_id: str = Query(...),
    filename: str = Query(...),
    user_email: str = Depends(get_authenticated_user)
):
    """Force downloads and OCR-processes a specific attachment."""
    from gmail.sync_engine import _fetch_and_save_attachment_locally
    from services.ocr_service import extract_attachment_text
    from db.repository import update_email_attachment_content, reset_refinement_status
    from cache.manager import get_user_lock
    import sqlite3
    
    # 1. Thread-safety: Lock the user to prevent background worker interference
    with get_user_lock(user_email):
        service = get_gmail_api_service(user_email)
        if not service:
            raise HTTPException(status_code=401, detail="Gmail service unauthorized")
            
        # 1. Resolve attachment metadata from DB
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT gmail_id, attachments FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        row = cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
        
    msg_id = row['gmail_id']
    atts = json.loads(row['attachments'] or '[]')
    
    # Find the specific attachment metadata (Handle both legacy strings and new dicts)
    target_att = None
    for att in atts:
        current_fname = att.get('filename') if isinstance(att, dict) else att
        if current_fname == filename:
            target_att = att if isinstance(att, dict) else {"filename": att, "original_name": att}
            break
            
    if not target_att:
        # Final Fuzzy Fallback: if filename doesn't match exactly, check if it's the original_name
        for att in atts:
            if isinstance(att, dict) and att.get('original_name') == filename:
                target_att = att
                break

    if not target_att:
        raise HTTPException(status_code=404, detail="Attachment metadata not found")

    # 2. Force Download (Use 20MB limit as requested for manual processing)
    # Note: 20MB is the practical limit for raw files in Gmail's 25MB encoded limit
    limit = 20 * 1024 * 1024
    local_path = _fetch_and_save_attachment_locally(service, msg_id, target_att, user_email, limit_bytes=limit)
    
    if not local_path:
        raise HTTPException(status_code=500, detail="Failed to download attachment (might exceed size limit)")

    # 3. Extract Text via OCR
    text = extract_attachment_text(local_path)
    if text:
        # CRITICAL: Use the stable, unique filename from metadata for the header key, 
        # not the potentially varying 'filename' parameter from the request.
        # We pass both the stable and original names to ensure the DB can sweep away any duplicates.
        stable_filename = target_att.get('filename') if isinstance(target_att, dict) else filename
        orig_filename = target_att.get('original_name') if isinstance(target_att, dict) else filename
        update_email_attachment_content(user_email, email_id, text, stable_filename, orig_filename)
        
        # 4. Reset AI Refinement status so it triggers again with new context
        reset_refinement_status(user_email, email_id)
        
        # 5. Notify UI of progress
        from core.notifier import SSE_NOTIFIER
        SSE_NOTIFIER.notify(user_email)
        
        return {"status": "success", "extracted_text": text[:100] + "..."}
    
    return {"status": "error", "detail": "OCR failed to find text"}
