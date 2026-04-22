import asyncio
import threading
import time
from typing import Dict, List, Any
from core.logging import get_logger

logger = get_logger("core.notifier")

class SSENotifier:
    """
    A thread-safe, multi-user event bus designed for Server-Sent Events (SSE).
    Allows background sync threads to broadcast 'refresh' signals to connected frontend clients.
    """
    def __init__(self):
        self._user_queues: Dict[str, List[asyncio.Queue]] = {}
        self._last_notify: Dict[str, float] = {} # For debouncing
        self._lock = threading.Lock()
        self._main_loop = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        """Sets the main FastAPI event loop context for thread-safe broadcasting."""
        self._main_loop = loop

    def subscribe(self, user_email: str) -> asyncio.Queue:
        """Creates a new broadcast queue for a connecting SSE client."""
        queue = asyncio.Queue()
        with self._lock:
            if user_email not in self._user_queues:
                self._user_queues[user_email] = []
            self._user_queues[user_email].append(queue)
        return queue

    def unsubscribe(self, user_email: str, queue: asyncio.Queue):
        """Removes a queue after a client disconnects."""
        with self._lock:
            if user_email in self._user_queues:
                if queue in self._user_queues[user_email]:
                    self._user_queues[user_email].remove(queue)
                if not self._user_queues[user_email]:
                    del self._user_queues[user_email]

    def notify(self, user_email: str, event_type: str = "refresh"):
        """
        Broadcasts an event to all connected clients for a specific user.
        Thread-safe: Can be called from any background worker thread.
        """
        if not self._main_loop:
            logger.warning(f"⚠️ [Notifier] No main loop set. Dropping signal for {user_email}.")
            return

        with self._lock:
            # Debounce: At most one update every 5 seconds per (user, event_type)
            debounce_key = f"{user_email}:{event_type}"
            now = time.time()
            if debounce_key in self._last_notify and (now - self._last_notify[debounce_key]) < 5:
                return
            self._last_notify[debounce_key] = now

            queues = self._user_queues.get(user_email, [])
            if not queues:
                return

            for q in queues:
                # Thread-safe scheduling into the async queue
                self._main_loop.call_soon_threadsafe(q.put_nowait, event_type)
        
        logger.debug(f"🔔 [Notifier] Broadcasted '{event_type}' to {len(queues)} clients for {user_email}")

# Singleton instance
SSE_NOTIFIER = SSENotifier()
