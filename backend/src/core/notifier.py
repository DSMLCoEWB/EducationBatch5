import asyncio
import threading
import time
import json
import redis
import redis.asyncio as aioredis
from typing import Dict, List, Any
from core.logging import get_logger
from config import CELERY_BROKER_URL, TASK_QUEUE_TYPE

logger = get_logger("core.notifier")

# Create a synchronous redis client for publishing (used by Celery workers)
_redis_publisher = None
if TASK_QUEUE_TYPE == "celery" and CELERY_BROKER_URL:
    try:
        _redis_publisher = redis.Redis.from_url(CELERY_BROKER_URL)
    except Exception as e:
        logger.error(f"Failed to initialize Redis publisher: {e}")

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
        If using Celery, publishes to Redis. Otherwise, routes locally.
        """
        if _redis_publisher:
            try:
                message = json.dumps({"user_email": user_email, "event_type": event_type})
                _redis_publisher.publish("sse_broadcast", message)
                logger.debug(f"🔔 [Notifier-Redis] Published '{event_type}' for {user_email}")
                return
            except Exception as e:
                logger.error(f"⚠️ [Notifier-Redis] Failed to publish event: {e}")

        # Fallback to local memory if Redis is not configured or failed
        if not self._main_loop:
            logger.warning(f"⚠️ [Notifier] No main loop set. Dropping signal for {user_email}.")
            return
            
        self._notify_local(user_email, event_type)
        
    def _notify_local(self, user_email: str, event_type: str):
        """Internal method to push events into local asyncio queues."""
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
                if self._main_loop:
                    self._main_loop.call_soon_threadsafe(q.put_nowait, event_type)
        
        logger.debug(f"🔔 [Notifier-Local] Broadcasted '{event_type}' to {len(queues)} clients for {user_email}")

    async def listen_for_redis_broadcasts(self):
        """Background task that runs in FastAPI to listen for Celery broadcasts."""
        if not CELERY_BROKER_URL or TASK_QUEUE_TYPE != "celery":
            return
            
        # Instantiate connection pool once outside the loop to prevent memory/socket leaks
        redis_client = aioredis.from_url(CELERY_BROKER_URL, health_check_interval=30)
        logger.info("📡 [Notifier-Redis] Listening for SSE broadcasts from Celery...")
        
        while True:
            pubsub = None
            try:
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("sse_broadcast")
                
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            user_email = data.get("user_email")
                            event_type = data.get("event_type")
                            if user_email and event_type:
                                self._notify_local(user_email, event_type)
                        except Exception as e:
                            logger.error(f"⚠️ [Notifier-Redis] Failed to process broadcast: {e}")
            except Exception as e:
                err_str = str(e).lower()
                if "timeout" in err_str:
                    logger.debug("🔄 [Notifier-Redis] Idle timeout reached. Reconnecting...")
                else:
                    logger.error(f"❌ [Notifier-Redis] Listener crashed: {e}. Reconnecting in 5s...")
            finally:
                if pubsub:
                    try:
                        await pubsub.close()
                    except:
                        pass
                await asyncio.sleep(5)

# Singleton instance
SSE_NOTIFIER = SSENotifier()
