import time
import random
import threading
from typing import List, Dict, Any
from datetime import datetime

from config import (
    SYNC_JITTER_SECONDS, GMAIL_SYNC_INTERVAL_SECONDS
)
from core.logging import get_logger
from core.context import worker_manager
from gmail.sync_engine import sync_gmail_incremental
from services.triage_service import get_batch_triage_ai
from services.ocr_service import extract_attachment_text
from db.repository import (
    get_unrefined_emails, update_email_refinement,
    get_unprocessed_attachments, update_email_attachment_content
)
from cache.manager import dynamic_cache_at_by_user

logger = get_logger("core.coordination")

def run_background_sync_loop(user_email: str):
    """
    Perpetual sync loop for a specific user.
    Implements randomized jitter, night-mode detection, and deep sleep recovery.
    """
    from db.repository import get_user_sync_history
    logger.info(f"🕵️ [StealthSync] Loop started for {user_email}")
    consecutive_errors = 0
    
    # [SAFETY]: 10-second pause before starting to prevent "Restart Storms"
    # This ensures we don't spam Google if the thread is flapping.
    time.sleep(10)
    
    while True:
        state = worker_manager.sync_workers.get(user_email, {})
        stop_flag = state.get("stop_flag", False)
        stop_event = state.get("stop_event")
        
        if stop_flag or not stop_event:
            break

        try:
            # 1. Fetch Dynamic User Preferences
            history = get_user_sync_history(user_email)
            base_interval = history.get("sync_interval_seconds", 300) if history else 300
            
            # 1b. Check for manual override (If updated in last 8 hours, skip Night Mode floor)
            updated_at_str = history.get("interval_updated_at")
            is_recently_manual = False
            if updated_at_str:
                try:
                    # SQLite CURRENT_TIMESTAMP is UTC
                    from datetime import datetime, timezone
                    from dateutil.parser import parse
                    updated_at = parse(updated_at_str).replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    if (now_utc - updated_at).total_seconds() < 28800: # 8 hour window
                        is_recently_manual = True
                except Exception: pass

            # 2. Night Mode Detection (11 PM to 7 AM)
            now_hour = datetime.now().hour # local hour for human context
            is_night = now_hour < 7 or now_hour >= 23
            
            if is_night and not is_recently_manual:
                base_interval = max(base_interval, 3600) # Minimum 1 hour at night
                logger.info(f"🌙 [StealthSync] Night Mode auto-active for {user_email}. Interval: 1h.")
            elif is_night and is_recently_manual:
                logger.info(f"⚡ [StealthSync] Respecting manual night override for {user_email} (Interval: {base_interval}s)")

            # 3. Randomized Jitter (Make polling intervals unpredictable)
            jitter = random.uniform(-SYNC_JITTER_SECONDS * 2, SYNC_JITTER_SECONDS * 2)
            wait_time = max(180, base_interval + jitter) # Hard floor of 3 mins
            
            # 4. Error Backoff & Deep Sleep
            if consecutive_errors > 0:
                # If we suspect a 429/Rate Limit, Deep Sleep for 2 hours
                deep_sleep = 7200 
                logger.warning(f"🚨 [StealthSync] Rate limit / Error detected. Entering DEEP SLEEP (2h) for {user_email}")
                if stop_event.wait(timeout=deep_sleep): break
                consecutive_errors = 0 # Reset after deep sleep
            
            # 5. Perform Sync
            result = sync_gmail_incremental(user_email)
            
            if result.get("status") == "success":
                consecutive_errors = 0
                if result.get("added", 0) > 0:
                    logger.info(f"📩 [StealthSync] New emails for {user_email}. Triggering enrichment.")
                    trigger_intelligence_suite(user_email)
                    # Notify UI to refresh local views after work is done
                    SSE_NOTIFIER.notify(user_email)
            else:
                consecutive_errors += 1
                
            # 6. Standard randomized sleep
            logger.debug(f"😴 [StealthSync] Cycle complete. Sleeping {wait_time:.1f}s for {user_email}")
            if stop_event.wait(timeout=wait_time): break # Interrupted by stop event
            
        except Exception as e:
            logger.error(f"❌ [StealthSync] Loop error for {user_email}: {e}")
            consecutive_errors += 1
            if stop_event.wait(timeout=300): break

def trigger_intelligence_suite(user_email: str):
    """
    Queues enrichment tasks to the WorkerManager if not already busy.
    """
    if worker_manager.is_intelligence_busy(user_email):
        return
        
    worker_manager.submit_intelligence_task(
        user_email, "ENRICHMENT", process_intelligence_backlog
    )

def process_intelligence_backlog(user_email: str):
    """
    The actual worker task that performs OCR and AI triage in batches.
    Loops until the backlog is cleared or a maximum catch-up limit is reached.
    """
    CATCHUP_MAX = 60 # Process up to 60 emails per cycle (in batches of 15)
    processed_count = 0
    
    try:
        # Phase A: OCR for attachments (Top 10)
        unprocessed_attachments = get_unprocessed_attachments(user_email, limit=10)
        for att in unprocessed_attachments:
            if worker_manager.should_stop_intelligence(user_email): break
            logger.info(f"🔍 [Enrichment] OCR for file: {att['filename']}")
            text = extract_attachment_text(att['local_path'])
            if text:
                update_email_attachment_content(user_email, att['email_id'], text, att['filename'])

        # Phase B: AI Triage (Catch-up Loop - 15 emails per minute)
        while processed_count < CATCHUP_MAX:
            if worker_manager.should_stop_intelligence(user_email): break
            
            unrefined = get_unrefined_emails(user_email, limit=15)
            if not unrefined:
                break
                
            logger.info(f"🧠 [Enrichment] Batch AI Triage: {len(unrefined)} emails ({processed_count}/{CATCHUP_MAX})")
            results = get_batch_triage_ai(unrefined)
            
            if not results:
                logger.warning("⚠️ [Enrichment] AI Triage returned empty results (likely rate limited).")
                break
                
            for email_id, data in results.items():
                update_email_refinement(
                    user_email, email_id, 
                    priority=data.get("priority"), 
                    category=data.get("category")
                )
            
            processed_count += len(unrefined)
            # Invalidate cache so UI sees new data
            dynamic_cache_at_by_user[user_email] = None 

    except Exception as e:
        logger.error(f"❌ [Enrichment] Error processing backlog for {user_email}: {e}")
