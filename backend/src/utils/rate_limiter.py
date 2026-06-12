import time
import threading
from config import GMAIL_CALLS_PER_MINUTE_LIMIT

class SimpleRateLimiter:
    """Proactive rate limiter to prevent Gmail API bursts."""
    def __init__(self, calls_per_minute: int):
        self.interval = 60.0 / calls_per_minute
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self.last_call = time.time()

# --- SINGLETON ---
GMAIL_RATE_LIMITER = SimpleRateLimiter(GMAIL_CALLS_PER_MINUTE_LIMIT)
