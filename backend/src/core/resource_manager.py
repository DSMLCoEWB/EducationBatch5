"""
AI Resource Manager (ARM)

This module implements a 'Human-First' traffic controller for AI hardware.
It prevents VRAM contention on resource-constrained GPUs (e.g., 4GB-8GB VRAM) 
by pausing non-critical background tasks when active user interaction is detected.

MECHANISM:
1. High Priority: Triggered by Chatbot or Manual Reply drafting. Sets a global
   lock and records the timestamp of the last interaction.
2. Yield/Wait: Background workers (OCR, Triage) check this lock before processing
   each item. If a human interaction occurred recently (default: 60s window),
   workers will pause and log a 'waiting' status.
3. Auto-Resume: Workers resume automatically once the human interaction window 
   has elapsed, ensuring background throughput without impacting user experience.
"""
import time
import os
import redis
import threading
from core.logging import get_logger

logger = get_logger("core.resources")

class AIResourceManager:
    def __init__(self):
        self._cooldown_seconds = 60 # Keep GPU reserved for 60s after last message
        self.use_redis = os.getenv("TASK_QUEUE_TYPE", "threadpool").lower() == "celery"
        self.redis = None
        
        if self.use_redis:
            try:
                redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
                self.redis = redis.from_url(redis_url)
            except Exception as e:
                logger.warning(f"Failed to connect to Redis for Resource Manager: {e}")
                self.redis = None
            
        # Fallback local state if redis is disabled or unavailable
        self._local_lock = threading.Lock()
        self._local_human_active = False
        self._local_last_activity: float = 0.0
    def acquire_high_priority(self):
        """Called by Chatbot or Manual Reply drafting to claim the GPU globally or locally."""
        if self.redis:
            try:
                # Set key with automatic expiration (cooldown)
                self.redis.setex("ai_gpu_human_lock", self._cooldown_seconds, "locked")
                logger.info("🔴 [Resource] GPU Reserved for Human (Global Redis Lock)")
                return
            except Exception as e:
                logger.warning(f"Redis lock failed: {e}")
                
        with self._local_lock:
            self._local_human_active = True
            self._local_last_activity = time.time()
            logger.info("🔴 [Resource] GPU Reserved for Human (Local Lock Fallback)")

    def is_human_using_gpu(self):
        """Checks if a human is currently active globally or locally."""
        if self.redis:
            try:
                is_locked = self.redis.exists("ai_gpu_human_lock")
                if is_locked:
                    return True
                else:
                    return False
            except Exception:
                pass
                
        with self._local_lock:
            if not self._local_human_active:
                return False
            
            if time.time() - self._local_last_activity > self._cooldown_seconds:
                self._local_human_active = False
                logger.info("🟢 [Resource] Human inactive. GPU returned to background pool.")
                return False
                
            return True

    def wait_for_gpu(self, task_label="Background Task"):
        """Called by background workers to wait for the human to finish."""
        if self.is_human_using_gpu():
            logger.info(f"⏳ [Resource] {task_label} paused. Human is using the GPU...")
            while self.is_human_using_gpu():
                time.sleep(10)
            logger.info(f"🚀 [Resource] Human finished. Resuming {task_label}.")

# Global Singleton
AI_RESOURCE_MANAGER = AIResourceManager()
