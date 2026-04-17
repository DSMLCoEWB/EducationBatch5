import os
import json
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

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # Enable WAL mode for high concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                gmail_id TEXT UNIQUE,
                thread_id TEXT,
                parent_email_id TEXT,
                sender TEXT,
                sender_email TEXT,
                recipient_email TEXT,
                subject TEXT,
                content TEXT,
                category TEXT,
                mail_type TEXT,
                priority INTEGER,
                date TEXT,
                has_attachment BOOLEAN,
                attachments TEXT,
                is_demo BOOLEAN,
                replied BOOLEAN,
                is_trashed BOOLEAN DEFAULT 0,
                is_inbox BOOLEAN DEFAULT 0,
                is_sent BOOLEAN DEFAULT 0,
                is_priority_refined BOOLEAN DEFAULT 0,
                is_ocr_processed BOOLEAN DEFAULT 0,
                attachment_content TEXT,
                followup_count INTEGER DEFAULT 0,
                institute_name TEXT,
                user_email TEXT,
                last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_last_synced ON emails(last_synced)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_user_email ON emails(user_email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_gmail_id ON emails(gmail_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_category ON emails (user_email, is_inbox, is_sent, is_trashed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_thread ON emails (user_email, thread_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS revoked_sessions (
                user_email TEXT PRIMARY KEY,
                revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                session_id TEXT,
                role TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sync_history (
                user_email TEXT PRIMARY KEY,
                last_history_id TEXT,
                last_sync_completed TIMESTAMP,
                consecutive_errors INTEGER DEFAULT 0,
                sync_interval_seconds INTEGER DEFAULT 600
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                sync_type TEXT,
                status TEXT,
                duration_ms INTEGER,
                messages_added INTEGER DEFAULT 0,
                messages_deleted INTEGER DEFAULT 0,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_audit_user ON sync_audit(user_email, timestamp)")
        
        # [SELF-HEALING]: Ensure 'has_attachment' is correctly set
        cursor.execute("""
            UPDATE emails 
            SET has_attachment = 1 
            WHERE (has_attachment = 0 OR has_attachment IS NULL) 
              AND (attachments IS NOT NULL AND attachments != '[]')
        """)

        # Migration logic (Ensure columns exist)
        _run_migrations(cursor)
        conn.commit()

def _run_migrations(cursor):
    """Internal helper to ensure all columns exist across app versions."""
    columns = {
        "parent_email_id": "TEXT",
        "is_priority_refined": "BOOLEAN DEFAULT 0",
        "is_inbox": "BOOLEAN DEFAULT 0",
        "is_sent": "BOOLEAN DEFAULT 0",
        "attachment_content": "TEXT",
        "is_ocr_processed": "BOOLEAN DEFAULT 0",
        "followup_count": "INTEGER DEFAULT 0",
        "recipient_email": "TEXT",
        "institute_name": "TEXT",
        "sync_interval_seconds": "INTEGER DEFAULT 300"
    }
    # Special case for tables other than 'emails'
    try:
        cursor.execute("SELECT sync_interval_seconds FROM user_sync_history LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE user_sync_history ADD COLUMN sync_interval_seconds INTEGER DEFAULT 300")
    try:
        cursor.execute("SELECT interval_updated_at FROM user_sync_history LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE user_sync_history ADD COLUMN interval_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    for col, definition in columns.items():
        try:
            cursor.execute(f"SELECT {col} FROM emails LIMIT 1")
        except sqlite3.OperationalError:
            print(f"[DB Migration] Adding {col} column...")
            cursor.execute(f"ALTER TABLE emails ADD COLUMN {col} {definition}")
