import sys
import os
from pathlib import Path

# Add src to python path so it can import correctly
sys.path.append(str(Path(__file__).parent / "src"))

from db.repository import init_db
from core.logging import get_logger

logger = get_logger("migrations")

import time

def run():
    logger.info("🚀 Starting Enterprise Database Migrations...")
    
    # Exponential backoff to wait for Postgres to become ready
    max_retries = 10
    retry_delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            init_db()
            logger.info("✅ Database successfully initialized.")
            return
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"❌ Database migration failed after {max_retries} attempts: {e}")
                sys.exit(1)
            logger.warning(f"⚠️ Database not ready (Attempt {attempt}/{max_retries}). Retrying in {retry_delay}s... ({e})")
            time.sleep(retry_delay)
            retry_delay *= 1.5

if __name__ == "__main__":
    run()
