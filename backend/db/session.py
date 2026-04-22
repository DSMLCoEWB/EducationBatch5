import sqlite3
from contextlib import contextmanager
from config import DB_PATH

@contextmanager
def get_db_conn():
    """Context manager for SQLite connections with proper safety defaults."""
    # follow the 'one connection per thread' pattern for safety in production.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        yield conn
    finally:
        conn.close()
