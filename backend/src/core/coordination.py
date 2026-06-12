import time
import random
import threading
from typing import List, Dict, Any
from datetime import datetime, timezone
from dateutil.parser import parse

from config import SYNC_JITTER_SECONDS
from core.logging import get_logger
from core.context import worker_manager
from core.notifier import SSE_NOTIFIER
from integrations.gmail.sync_engine import sync_gmail_incremental
from integrations.microsoft.sync_engine import sync_microsoft_incremental
from services.triage_service import get_batch_triage_ai
from services.ocr_service import extract_attachment_text
from db.repository import (
    get_unrefined_emails, update_email_refinement,
    get_unprocessed_attachments, update_email_attachment_content,
    has_enrichment_work
)
from cache.manager import (
    get_user_lock
)

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
            from config import GLOBAL_SYNC_INTERVAL_SECONDS
            base_interval = history.get("sync_interval_seconds") or GLOBAL_SYNC_INTERVAL_SECONDS if history else GLOBAL_SYNC_INTERVAL_SECONDS
            
            # 1b. Check for manual override (If updated in last 8 hours, skip Night Mode floor)
            updated_at_str = history.get("interval_updated_at") if history else None
            is_recently_manual = False
            if updated_at_str:
                try:
                    # SQLite CURRENT_TIMESTAMP is UTC
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
                from config import SYNC_MAX_BACKOFF_SECONDS
                # Exponential backoff: min(300 * 2^(errors-1), MAX_BACKOFF)
                backoff = min(300 * (2 ** (consecutive_errors - 1)), SYNC_MAX_BACKOFF_SECONDS)
                logger.warning(f"🚨 [StealthSync] Error detected ({consecutive_errors} errors). Backing off for {backoff}s for {user_email}")
                if stop_event.wait(timeout=backoff): break
                # Note: We do NOT reset consecutive_errors here. It only resets on success (Line 103).
            
            # 5. Perform Sync
            # 1. Start Signal (Visual Heartbeat in UI)
            SSE_NOTIFIER.notify(user_email, "sync_started")
            
            logger.info(f"🔄 [Sync] Starting background cycle for {user_email}")
            provider = history.get("auth_provider", "google") if history else "google"
            if provider == "microsoft":
                result = sync_microsoft_incremental(user_email)
            else:
                result = sync_gmail_incremental(user_email)
            
            # 2. End Signal / UI Refresh
            SSE_NOTIFIER.notify(user_email, "sync_complete")
            
            if result.get("status") == "success":
                consecutive_errors = 0
                # Trigger enrichment if NEW emails were added OR if there's an existing backlog
                if result.get("added", 0) > 0 or has_enrichment_work(user_email):
                    logger.info(f"📩 [StealthSync] Enrichment required for {user_email}. Triggering intelligence suite.")
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
    """Entry point to launch the AI intelligence worker for a specific user."""
    with get_user_lock(user_email):
        if worker_manager.is_intelligence_busy(user_email, "ENRICHMENT"):
            logger.info(f"⏳ [Intelligence] Worker already active for {user_email}. Skipping trigger.")
            return
            
        logger.info(f"🧠 [Intelligence] Spawning background worker for {user_email}...")
        worker_manager.submit_intelligence_task(
            user_email, 
            "ENRICHMENT", 
            process_intelligence_backlog
        )
        logger.debug(f"✅ [Intelligence] Task submitted to ThreadPool for {user_email}.")

def process_intelligence_backlog(user_email: str):
    """
    The actual worker task that performs OCR and AI triage in batches.
    Processes batches until clear, sleeping between batches to respect rate limits.
    """
    from config import AI_BATCH_SIZE, PRIORITY_LLM_WINDOW_SECONDS
    import time
    
    try:
        # Phase A: OCR for attachments (Top 10) - Independent Fault Tolerance
        try:
            unprocessed_attachments = get_unprocessed_attachments(user_email, limit=10)
            if unprocessed_attachments:
                logger.info(f"🔍 [Worker] Found {len(unprocessed_attachments)} pending attachments for OCR.")
                
            for att in unprocessed_attachments:
                if worker_manager.should_stop_intelligence(user_email): return
                
                logger.info(f"🛰️ [OCR-Worker] Processing: {att['filename']}")
                try:
                    text = extract_attachment_text(att['local_path'])
                    # Even if text is empty, we must mark it as processed to avoid infinite retries
                    update_email_attachment_content(
                        user_email, att['email_id'], text or "", 
                        att['filename'], att.get('original_name')
                    )
                except Exception as file_err:
                    logger.error(f"❌ [OCR-Worker] Extraction failed for {att['filename']}: {file_err}")
                    # Mark as processed with failure marker to prevent blockages
                    update_email_attachment_content(
                        user_email, att['email_id'], "[OCR FAILED]", 
                        att['filename'], att.get('original_name')
                    )
                    
        except Exception as ocr_err:
            logger.error(f"⚠️ [Enrichment] OCR Phase failed: {ocr_err}")

        # Phase B: AI Triage (Self-pacing loop) - Independent Fault Tolerance
        try:
            while not worker_manager.should_stop_intelligence(user_email):
                unrefined = get_unrefined_emails(user_email, limit=AI_BATCH_SIZE)
                if not unrefined:
                    break
                    
                logger.info(f"🧠 [Enrichment] Batch AI Triage: {len(unrefined)} emails.")
                results = get_batch_triage_ai(unrefined, user_email)
                
                if results:
                    refined_count = 0
                    for email_id, data in results.items():
                        count = update_email_refinement(
                            user_email, email_id, 
                            priority=data.get("priority"), 
                            category=data.get("category")
                        )
                        if count: refined_count += 1
                        
                    logger.info(f"✅ [Enrichment] Successfully refined {refined_count} of {len(results)} emails in batch.")
                    
                    # Notify UI of refinement progress
                    SSE_NOTIFIER.notify(user_email, "refinement_progress")
                    
                    # Check for more work
                    more_work = get_unrefined_emails(user_email, limit=1)
                    if more_work:
                        from config import AI_PREFER_LOCAL
                        # Local models don't need 60s API rests, just a small breather for GPU/UI responsiveness
                        rest_seconds = 5 if AI_PREFER_LOCAL else (PRIORITY_LLM_WINDOW_SECONDS + 1)
                        logger.info(f"😴 [Enrichment] Backlog remaining. Resting {rest_seconds}s...")
                        time.sleep(rest_seconds)
                    else:
                        break
                else:
                    # If rate limited or empty, wait and try again or exit cycle
                    from config import AI_PREFER_LOCAL
                    rest_seconds = 5 if AI_PREFER_LOCAL else (PRIORITY_LLM_WINDOW_SECONDS + 1)
                    logger.warning(f"⚠️ [Enrichment] AI Triage limit reached/empty. Cooling down {rest_seconds}s.")
                    time.sleep(rest_seconds)
        except Exception as ai_err:
            logger.error(f"⚠️ [Enrichment] AI Triage Phase failed: {ai_err}")

    except Exception as e:
        logger.error(f"❌ [Enrichment] Error processing backlog for {user_email}: {e}")
