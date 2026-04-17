import threading
import pandas as pd
from datetime import datetime
from typing import Dict, Any

# --- CACHE STORAGE ---
# [SINGLETONS] These must remain unique across the entire process
user_display_name_cache: Dict[str, str] = {}
dynamic_cache_df_by_user: Dict[str, pd.DataFrame] = {}
dynamic_cache_at_by_user: Dict[str, datetime] = {}
is_syncing_by_user: Dict[str, bool] = {}
llm_refined_cache: Dict[str, Dict[str, Any]] = {} 

# --- LOCKING ---
# [SINGLETONS]
user_locks: Dict[str, threading.Lock] = {}
user_locks_main_lock = threading.Lock()

def get_user_lock(user_email: str) -> threading.Lock:
    """Gets or creates a per-user lock in a thread-safe manner."""
    with user_locks_main_lock:
        if user_email not in user_locks:
            user_locks[user_email] = threading.Lock()
        return user_locks[user_email]

def user_key(user_email: str) -> str:
    """Helper to ensure consistent keys for user-specific data."""
    return user_email.strip().lower()
