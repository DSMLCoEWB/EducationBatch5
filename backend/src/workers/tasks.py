import random
from datetime import datetime, timezone
from dateutil.parser import parse
from celery import shared_task
from core.logging import get_logger
from integrations.gmail.sync_engine import sync_gmail_incremental
from db.repository import get_user_sync_history, has_enrichment_work
from core.notifier import SSE_NOTIFIER

logger = get_logger("workers.tasks")

@shared_task(name="workers.tasks.run_background_sync_task")
def run_background_sync_task(user_email: str, consecutive_errors: int = 0):
    """Celery task executing a single background sync cycle and scheduling the next cycle recursively."""
    from core.context import worker_manager
    
    # When using Celery, the stop flag is managed via Redis to support multi-process environments.
    from config import TASK_QUEUE_TYPE
    if TASK_QUEUE_TYPE == "celery":
        from cache.manager import redis_client
        if redis_client:
            stop_flag = redis_client.get(f"stop_sync_{user_email}")
            if stop_flag == "1":
                logger.info(f"🛑 [CelerySync] Sync loop stopped for {user_email}. Exiting worker task.")
                return
    else:
        if not worker_manager.is_sync_running(user_email):
            logger.info(f"🛑 [CelerySync] Sync loop stopped for {user_email}. Exiting worker task.")
            return

    try:
        # 1. Fetch user intervals and preferences
        history = get_user_sync_history(user_email)
        from config import GLOBAL_SYNC_INTERVAL_SECONDS
        base_interval = history.get("sync_interval_seconds") or GLOBAL_SYNC_INTERVAL_SECONDS if history else GLOBAL_SYNC_INTERVAL_SECONDS
        
        # 2. Check for manual overrides and Night Mode
        updated_at_str = history.get("interval_updated_at") if history else None
        is_recently_manual = False
        if updated_at_str:
            try:
                updated_at = parse(updated_at_str).replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if (now_utc - updated_at).total_seconds() < 28800: # 8 hours
                    is_recently_manual = True
            except Exception:
                pass

        now_hour = datetime.now().hour
        is_night = now_hour < 7 or now_hour >= 23
        
        if is_night and not is_recently_manual:
            base_interval = max(base_interval, 3600)  # 1 hour minimum at night

        # 3. Add Jitter
        from config import SYNC_JITTER_SECONDS
        jitter = random.uniform(-SYNC_JITTER_SECONDS * 2, SYNC_JITTER_SECONDS * 2)
        wait_time = max(180, base_interval + jitter)

        # 4. Trigger Sync Start in UI
        SSE_NOTIFIER.notify(user_email, "sync_started")
        logger.info(f"🔄 [CelerySync] Starting incremental sync for {user_email}")
        
        from cache.manager import get_user_lock
        with get_user_lock(user_email):
            provider = history.get("auth_provider", "google") if history else "google"
            if provider == "microsoft":
                from integrations.microsoft.sync_engine import sync_microsoft_incremental
                result = sync_microsoft_incremental(user_email)
            else:
                result = sync_gmail_incremental(user_email)
            
        SSE_NOTIFIER.notify(user_email, "sync_complete")
        
        next_countdown = wait_time
        if result.get("status") == "success":
            consecutive_errors = 0
            # Trigger enrichment if there is work to do
            if result.get("added", 0) > 0 or has_enrichment_work(user_email):
                logger.info(f"📩 [CelerySync] Backlog detected. Triggering Celery intelligence suite.")
                process_intelligence_backlog_task.delay(user_email)
                SSE_NOTIFIER.notify(user_email)
        else:
            consecutive_errors += 1
            from config import SYNC_MAX_BACKOFF_SECONDS
            # Exponential backoff on errors
            next_countdown = min(300 * (2 ** (consecutive_errors - 1)), SYNC_MAX_BACKOFF_SECONDS)
            logger.warning(f"🚨 [CelerySync] Sync cycle returned error status ({consecutive_errors} errors). Backing off for {next_countdown}s.")

        # 5. Enqueue the next sync cycle recursively
        run_background_sync_task.apply_async((user_email, consecutive_errors), countdown=next_countdown)
        logger.info(f"😴 [CelerySync] Cycle complete. Next sync scheduled in {next_countdown:.1f}s.")

    except Exception as e:
        logger.error(f"❌ [CelerySync] Task execution error for {user_email}: {e}")
        consecutive_errors += 1
        from config import SYNC_MAX_BACKOFF_SECONDS
        next_countdown = min(300 * (2 ** (consecutive_errors - 1)), SYNC_MAX_BACKOFF_SECONDS)
        run_background_sync_task.apply_async((user_email, consecutive_errors), countdown=next_countdown)


@shared_task(name="workers.tasks.process_intelligence_backlog_task")
def process_intelligence_backlog_task(user_email: str):
    """Celery task running the intelligence suite backlog (OCR & Triage) for a user."""
    from cache.manager import get_user_lock
    lock = get_user_lock(user_email)
    
    # Try to acquire lock. If another worker is already processing this user, skip!
    if not lock.acquire(blocking=False):
        logger.info(f"⏳ [CeleryIntel] Intelligence task already running for {user_email}. Skipping duplicate.")
        return
        
    try:
        from core.coordination import process_intelligence_backlog
        logger.info(f"🧠 [CeleryIntel] Running intelligence backlog processing for {user_email}...")
        process_intelligence_backlog(user_email)
    except Exception as e:
        logger.error(f"❌ [CeleryIntel] Backlog processing error for {user_email}: {e}")
    finally:
        try:
            lock.release()
        except Exception:
            pass
