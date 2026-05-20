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
import threading
import time
from core.logging import get_logger

logger = get_logger("core.resources")

class AIResourceManager:
    def __init__(self):
        self._human_active = False
        self._lock = threading.Lock()
        self._last_human_activity = 0
        self._cooldown_seconds = 60 # Keep GPU reserved for 60s after last message

    def acquire_high_priority(self):
        """Called by Chatbot to claim the GPU."""
        with self._lock:
            self._human_active = True
            self._last_human_activity = time.time()
            logger.info("🔴 [Resource] GPU Reserved for Human (High Priority)")

    def is_human_using_gpu(self):
        """Checks if a human is currently active or in cooldown."""
        with self._lock:
            if not self._human_active:
                return False
            
            # Check for inactivity timeout (Auto-release after 60s)
            if time.time() - self._last_human_activity > self._cooldown_seconds:
                self._human_active = False
                logger.info("🟢 [Resource] Human inactive. GPU returned to background pool.")
                return False
                
            return True

    def wait_for_gpu(self, task_label="Background Task"):
        """Called by background workers to wait for the human to finish."""
        if self.is_human_using_gpu():
            logger.info(f"⏳ [Resource] {task_label} paused. Human is using the Chatbot...")
            while self.is_human_using_gpu():
                time.sleep(10)
            logger.info(f"🚀 [Resource] Human finished. Resuming {task_label}.")

# Global Singleton
AI_RESOURCE_MANAGER = AIResourceManager()
