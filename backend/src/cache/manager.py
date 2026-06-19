import threading
from typing import Dict, Any
import redis
from config import CELERY_BROKER_URL, TASK_QUEUE_TYPE

# --- REDIS CLIENT ---
# We use the same Redis broker as Celery to store distributed locks
redis_client = None
if CELERY_BROKER_URL:
    try:
        redis_client = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)
    except Exception as e:
        pass

# --- LOCKING ---
# [SINGLETONS]
user_locks: Dict[str, threading.Lock] = {}
user_locks_main_lock = threading.Lock()

def get_user_lock(user_email: str):
    """
    Gets a lock for a specific user to prevent concurrent sync operations.
    If using Celery, returns a distributed Redis lock.
    If using threadpool (Edge Mode), returns a local threading.Lock.
    """
    if TASK_QUEUE_TYPE == "celery" and redis_client:
        lock_key = f"sync_lock_{user_key(user_email)}"
        # Timeout of 300 seconds prevents deadlocks if a worker crashes while holding the lock
        return redis_client.lock(lock_key, timeout=300)
    else:
        # Edge Mode Fallback
        with user_locks_main_lock:
            if user_email not in user_locks:
                user_locks[user_email] = threading.Lock()
            return user_locks[user_email]

def user_key(user_email: str) -> str:
    """Helper to ensure consistent keys for user-specific data."""
    return user_email.strip().lower()
