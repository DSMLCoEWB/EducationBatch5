import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Set, Any
from core.logging import get_logger
from config import TASK_QUEUE_TYPE
from cache.manager import get_user_lock
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



    def _is_sync_running_nolock(self, user_email: str) -> bool:
        if TASK_QUEUE_TYPE == "celery":
            from cache.manager import redis_client
            if redis_client:
                # Distributed check to prevent multiple Nginx replicas from starting loops
                return bool(redis_client.get(f"sync_loop_active_{user_email}"))

        state = self.sync_workers.get(user_email)
        if not state:
            return False
        if state.get("is_celery"):
            return not state.get("stop_flag", False)
        thread = state.get("thread")
        return bool(thread and thread.is_alive() and not state.get("stop_flag", False))

    def is_sync_running(self, user_email: str) -> bool:
        with self._lock:
            return self._is_sync_running_nolock(user_email)

    def start_sync_worker(self, user_email: str, target_fn: Any):
        with self._lock:
            if self._is_sync_running_nolock(user_email):
                logger.debug(f"🔁 [WorkerManager] Sync worker already alive for {user_email}. Skipping.")
                return
            
            if TASK_QUEUE_TYPE == "celery":
                # Send Celery task
                from workers.tasks import run_background_sync_task
                from cache.manager import redis_client
                
                if redis_client:
                    redis_client.delete(f"stop_sync_{user_email}")
                    # Immediately claim the distributed lock so other replicas don't overlap
                    redis_client.set(f"sync_loop_active_{user_email}", "1", ex=1200)
                    
                self.sync_workers[user_email] = {"is_celery": True}
                run_background_sync_task.delay(user_email)
                logger.info(f"🚀 [WorkerManager] Dispatched sync task to Celery for {user_email}.")
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
            logger.info(f"🚀 [WorkerManager] Launched local sync worker for {user_email}.")

    def stop_sync_worker(self, user_email: str):
        """Signals the sync worker for a user to stop gracefully."""
        with self._lock:
            if user_email in self.sync_workers:
                worker_info = self.sync_workers.pop(user_email)
                
                if TASK_QUEUE_TYPE == "celery":
                    from cache.manager import redis_client
                    if redis_client:
                        redis_client.set(f"stop_sync_{user_email}", "1")
                        redis_client.delete(f"sync_loop_active_{user_email}")
                        
                logger.info(f"🛑 [WorkerManager] Sent stop signal to sync worker for {user_email}")
                
                if "stop_event" in worker_info:
                    worker_info["stop_event"].set()
                    
            if user_email in self.intelligence_stop_events:
                self.intelligence_stop_events[user_email].set()

    def should_stop_intelligence(self, user_email: str) -> bool:
        if TASK_QUEUE_TYPE == "celery":
            return False
        event = self.intelligence_stop_events.get(user_email)
        return event.is_set() if event else False

    def is_intelligence_busy(self, user_email: str, task_type: str = "ANY") -> bool:
        if TASK_QUEUE_TYPE == "celery":
            return False
        with self._lock:
            active = self.active_tasks.get(user_email, set())
            if task_type == "ANY":
                return len(active) > 0
            return task_type in active

    def submit_intelligence_task(self, user_email: str, task_type: str, task_fn: Any):
        with self._lock:
            if TASK_QUEUE_TYPE == "celery":
                from workers.tasks import process_intelligence_backlog_task
                process_intelligence_backlog_task.delay(user_email)
                logger.info(f"🚀 [WorkerManager] Dispatched intelligence task to Celery for {user_email}.")
                return

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



    def stop_all(self):
        """Cleanly shuts down all active background threads and executors."""
        logger.info("🛑 [WorkerManager] Initiating global shutdown sequence...")
        with self._lock:
            for user_email in list(self.sync_workers.keys()):
                self.sync_workers[user_email]["stop_flag"] = True
                if "stop_event" in self.sync_workers[user_email]:
                    self.sync_workers[user_email]["stop_event"].set()
            for event in self.intelligence_stop_events.values():
                event.set()
                
        self.executor.shutdown(wait=False, cancel_futures=True)
        logger.info("✅ [WorkerManager] All background workers halted.")
