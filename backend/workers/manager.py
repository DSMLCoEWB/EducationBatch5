import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Set, Any
from core.logging import get_logger
from config import CACHE_TTL_SECONDS, MAX_CACHE_ENTRIES, CLEANUP_INTERVAL_SECONDS
from cache.manager import (
    dynamic_cache_at_by_user, dynamic_cache_df_by_user, 
    get_user_lock, is_syncing_by_user, llm_refined_cache,
    user_display_name_cache
)
from core.gmail_context import GMAIL_SERVICE_MAP, GMAIL_SERVICE_LOCK

logger = get_logger("workers")

class WorkerManager:
    """Central manager for thread-safe background worker lifecycle and task deduplication."""
    def __init__(self):
        self._lock = threading.Lock()
        # Perpetual sync workers: user_email -> {"thread": Thread, "stop_flag": bool}
        self.sync_workers: Dict[str, Dict[str, Any]] = {}
        # Task workers tracking: user_email -> set(task_type, ...)
        self.active_tasks: Dict[str, Set[str]] = {}
        # Thread-safe stop events for intelligence tasks: user_email -> threading.Event
        self.intelligence_stop_events: Dict[str, threading.Event] = {}

        # Core executor for short-lived enrichment tasks
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="intelligence-worker")

        # [MAINTENANCE LAYER]
        self.stop_maintenance = threading.Event()
        self.maintenance_thread = threading.Thread(
            target=self._background_maintenance_loop,
            daemon=True,
            name="worker-maintenance"
        )
        self.maintenance_thread.start()
        logger.info(f"🛠️ [WorkerManager] Maintenance thread started.")

    def _is_sync_running_nolock(self, user_email: str) -> bool:
        state = self.sync_workers.get(user_email)
        if not state:
            return False
        thread = state.get("thread")
        return thread and thread.is_alive() and not state.get("stop_flag", False)

    def is_sync_running(self, user_email: str) -> bool:
        with self._lock:
            return self._is_sync_running_nolock(user_email)

    def start_sync_worker(self, user_email: str, target_fn: Any):
        with self._lock:
            if self._is_sync_running_nolock(user_email):
                logger.debug(f"🔁 [WorkerManager] Sync worker already alive for {user_email}. Skipping.")
                return
            
            self.sync_workers[user_email] = {
                "stop_flag": False,
                "stop_event": threading.Event()
            }
            thread = threading.Thread(
                target=target_fn,
                args=(user_email,),
                daemon=True,
                name=f"sync-{user_email[:8]}"
            )
            self.sync_workers[user_email]["thread"] = thread
            thread.start()
            logger.info(f"🚀 [WorkerManager] Launched sync worker for {user_email}.")

    def stop_sync_worker(self, user_email: str):
        with self._lock:
            if user_email in self.sync_workers:
                self.sync_workers[user_email]["stop_flag"] = True
                self.sync_workers[user_email]["stop_event"].set()
            if user_email in self.intelligence_stop_events:
                self.intelligence_stop_events[user_email].set()

    def should_stop_intelligence(self, user_email: str) -> bool:
        event = self.intelligence_stop_events.get(user_email)
        return event.is_set() if event else False

    def is_intelligence_busy(self, user_email: str, task_type: str = "ANY") -> bool:
        with self._lock:
            active = self.active_tasks.get(user_email, set())
            if task_type == "ANY":
                return len(active) > 0
            return task_type in active

    def submit_intelligence_task(self, user_email: str, task_type: str, task_fn: Any):
        with self._lock:
            tasks = self.active_tasks.setdefault(user_email, set())
            if task_type in tasks:
                return
            
            if user_email not in self.intelligence_stop_events:
                self.intelligence_stop_events[user_email] = threading.Event()
            else:
                self.intelligence_stop_events[user_email].clear()

            tasks.add(task_type)
            
        def _task_wrapper():
            try:
                task_fn(user_email)
            finally:
                with self._lock:
                    if user_email in self.active_tasks:
                        self.active_tasks[user_email].discard(task_type)
                        if not self.active_tasks[user_email]:
                            del self.active_tasks[user_email]
        
        self.executor.submit(_task_wrapper)

    def _background_maintenance_loop(self):
        while not self.stop_maintenance.wait(timeout=CLEANUP_INTERVAL_SECONDS):
            try:
                self._perform_cache_cleanup()
            except Exception as e:
                logger.error(f"❌ [WorkerManager] Maintenance cycle error: {e}")

    def _perform_cache_cleanup(self):
        now = datetime.now()
        to_evict = []
        keys_snapshot = list(dynamic_cache_at_by_user.keys())

        for key in keys_snapshot:
            lock = get_user_lock(key)
            with lock:
                stamp = dynamic_cache_at_by_user.get(key)
                if stamp is None or (now - stamp).total_seconds() > CACHE_TTL_SECONDS:
                    to_evict.append(key)

        if len(dynamic_cache_at_by_user) > MAX_CACHE_ENTRIES:
            sorted_keys = sorted(dynamic_cache_at_by_user.items(), key=lambda x: x[1])
            for key, _ in sorted_keys[:len(dynamic_cache_at_by_user) - MAX_CACHE_ENTRIES]:
                if key not in to_evict:
                    to_evict.append(key)

        for key in set(to_evict):
            lock = get_user_lock(key)
            with GMAIL_SERVICE_LOCK:
                with lock:
                    stamp = dynamic_cache_at_by_user.get(key)
                    if stamp is not None and (now - stamp).total_seconds() < 60:
                        continue
                    dynamic_cache_df_by_user.pop(key, None)
                    dynamic_cache_at_by_user.pop(key, None)
                    if stamp is None or (now - stamp).total_seconds() > CACHE_TTL_SECONDS:
                        GMAIL_SERVICE_MAP.pop(key, None)
                    llm_refined_cache.pop(key, None)
                    user_display_name_cache.pop(key, None)
