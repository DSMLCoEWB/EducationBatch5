from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import json
import os
import asyncio
from datetime import datetime

from core.dependencies import get_authenticated_user
from db.repository import (
    get_db_conn, update_sync_interval, get_user_sync_history,
    mark_as_trashed, get_emails_from_db, get_refinement_stats,
    get_categories_from_db, get_dashboard_stats
)
from utils.seeding import (
    send_demo_emails_to_gmail_inbox, cleanup_seeded_emails,
    send_excel_emails_to_gmail_inbox
)
from gmail.sync_engine import sync_gmail_incremental
from gmail.client import get_gmail_api_service
from core.notifier import SSE_NOTIFIER
from core.coordination import trigger_intelligence_suite, run_background_sync_loop
from core.context import worker_manager
from config import FILES_DIR

router = APIRouter(prefix="/emails", tags=["Emails"])

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
    with get_db_conn() as conn:
        import sqlite3
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE thread_id = ? AND user_email = ? ORDER BY date ASC", (thread_id, user_email))
        rows = [dict(r) for r in cursor.fetchall()]
        if not rows:
             raise HTTPException(status_code=404, detail="Thread not found")
        return rows

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
                try:
                    service.users().messages().trash(userId="me", id=row[0]).execute()
                    # Notify UI to refresh local view
                    SSE_NOTIFIER.notify(user_email)
                except Exception: pass
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
                try:
                    service.users().messages().untrash(userId="me", id=row[0]).execute()
                    # Notify UI to refresh local view
                    SSE_NOTIFIER.notify(user_email)
                except Exception: pass
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
        if elapsed < 120:
             raise HTTPException(
                 status_code=429, 
                 detail=f"Cooldown active. Please wait {int(120 - elapsed)}s for stealth protection."
             )

    if not worker_manager.is_sync_running(user_email):
        worker_manager.start_sync_worker(user_email, run_background_sync_loop)
    
    # Immediate incremental sync in foreground for respondiveness
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

@router.post("/seed-demo")
def seed_demo(user_email: str = Depends(get_authenticated_user)):
    """Injects demo emails into the inbox for testing."""
    return send_demo_emails_to_gmail_inbox(user_email)

@router.post("/seed-excel")
def seed_excel(user_email: str = Depends(get_authenticated_user)):
    """Parses grievances.xlsx and seeds those emails into Gmail."""
    return send_excel_emails_to_gmail_inbox(user_email)

@router.post("/cleanup-seeded")
def cleanup_seeded(user_email: str = Depends(get_authenticated_user)):
    """Trashes emails with [DEMO] prefix."""
    return cleanup_seeded_emails(user_email)

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
    from gmail.client import get_gmail_api_service
    import base64
    from email.mime.text import MIMEText
    
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    message = MIMEText(payload.body)
    message['to'] = payload.to_email
    message['subject'] = payload.subject
    raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    try:
        sent_msg = service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
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
    from gmail.client import get_gmail_api_service
    import base64
    from email.mime.text import MIMEText
    
    service = get_gmail_api_service(user_email)
    if not service:
        raise HTTPException(status_code=401)
        
    to_email = payload.get("to_email")
    subject = payload.get("original_subject", "")
    body = payload.get("reply_text", "")
    email_id = payload.get("email_id")
    
    # 1. Thread Reconciliation: Look up actual thread data from DB
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT gmail_id, thread_id FROM emails WHERE id = ?", (email_id,))
        row = cursor.fetchone()
        
    actual_gmail_id = row[0] if row else None
    actual_thread_id = row[1] if row else None

    # 2. Construct MIME message
    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject if subject.startswith("Re:") else f"Re: {subject}"
    
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
def list_colleges():
    """Returns the list of registered Colleges/Institutions."""
    import json
    from config import DATA_DIR
    path = os.path.join(DATA_DIR, "colleges.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return {"colleges": json.load(f)}
    return {"colleges": []}

@router.get("/download/{eml_filename}")
def download_eml(eml_filename: str):
    """Provides original .eml files for specialized workflows."""
    path = os.path.join(FILES_DIR, eml_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="message/rfc822")
