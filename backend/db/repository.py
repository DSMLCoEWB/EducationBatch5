import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from config import DB_PATH
from db.session import get_db_conn

def mark_as_trashed(user_email: str, email_id: str, is_trashed: bool = True):
    """Mark an email as trashed in the local database for a specific user."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if is_trashed:
            cursor.execute(
                "UPDATE emails SET is_trashed = 1, category = 'trash' WHERE id = ? AND user_email = ?", 
                (email_id, user_email)
            )
        else:
            cursor.execute(
                "UPDATE emails SET is_trashed = 0, is_inbox = 1, category = 'Miscellaneous' WHERE id = ? AND user_email = ?", 
                (email_id, user_email)
            )
        conn.commit()

def get_emails_from_db(user_email: str, category: str = 'all', is_demo: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Retrieve emails from the database with filtering and TypeScript-ready mapping."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Map legacy frontend IDs to actual DB category strings
        category_map = {
            'suspension': 'Suspension / Disciplinary',
            'legal': 'Legal Issues',
            'fir': 'Legal Issues',
            'rti': 'RTI Matters',
            'cmo': 'CMO Issues',
            'semester': 'Semester / Examination',
            'exam': 'Semester / Examination',
            'scholarship': 'Scholarship & Fee Concession',
            'purchase': 'Purchase / Procurement Issues',
            'cash': 'Cash Issues',
            'ragging': 'Anti-Ragging Complaints',
            'accreditation': 'Accreditation & Ranking',
            'service': 'Service Matters',
            'appointment': 'Appointment Issues',
            'transfer': 'Transfer Cases',
            'inspection': 'Inspection Matters',
            'seat-matrix': 'Seat Matrix Issues',
            'miscellaneous': 'Miscellaneous'
        }
        db_category = category_map.get(category, category)
        
        query = "SELECT * FROM emails WHERE user_email = ?"
        params = [user_email]
        
        if category == 'trash':
            query += " AND is_trashed = 1"
        elif category == 'dashboard':
            query += " AND (is_inbox = 1 OR is_sent = 1) AND is_trashed = 0"
        elif category == 'all':
            query += " AND is_inbox = 1 AND is_trashed = 0"
        elif category == 'Sent':
            query += " AND is_sent = 1 AND is_trashed = 0"
        elif category == 'miscellaneous':
            main_categories = [
                'Suspension / Disciplinary', 'Legal Issues', 'RTI Matters', 'CMO Issues',
                'Semester / Examination', 'Scholarship & Fee Concession', 'Purchase / Procurement Issues',
                'Cash Issues', 'Anti-Ragging Complaints', 'Accreditation & Ranking', 'Service Matters',
                'Appointment Issues', 'Transfer Cases', 'Inspection Matters', 'Seat Matrix Issues'
            ]
            placeholders = ', '.join(['?'] * len(main_categories))
            query += f" AND category NOT IN ({placeholders}) AND is_inbox = 1 AND is_trashed = 0"
            params.extend(main_categories)
        else:
            query += " AND category = ? AND is_inbox = 1 AND is_trashed = 0"
            params.append(db_category)
            
        if is_demo is not None:
            query += " AND is_demo = ?"
            params.append(1 if is_demo else 0)
            
        query += " ORDER BY priority ASC, date DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
    result = [map_email_row(row) for row in rows]
    return result

def map_email_row(row: Any) -> Dict[str, Any]:
    """Standardizes mapping from DB row to frontend-ready JSON object."""
    email = dict(row)
    # Type Conversion for Frontend Parity
    email['email_id']      = email['id']
    email['parentEmailId'] = email.get('parent_email_id')
    email['threadId']      = email.get('thread_id')
    email['mailType']      = email.get('mail_type')
    email['followUpCount'] = email.get('followup_count', 0)
    email['emailDate']     = email.get('date')
    email['senderEmail']    = email.get('sender_email')
    email['recipientEmail'] = email.get('recipient_email')
    email['instituteName']  = email.get('institute_name')
    email['html_content']   = email.get('html_content')
    
    email['hasAttachment'] = bool(email.get('has_attachment'))
    email['is_demo']       = bool(email.get('is_demo'))
    email['replied']       = bool(email.get('replied'))
    
    # Critical: Ensure attachments is always a real list for frontend .map()
    atts = email.get('attachments')
    if isinstance(atts, str):
        try:
            email['attachments'] = json.loads(atts or '[]')
        except Exception:
            email['attachments'] = []
    else:
        email['attachments'] = atts or []
        
    return email

def get_thread_from_db(user_email: str, thread_id: str) -> List[Dict[str, Any]]:
    """Retrieves all emails in a thread with standardized mapping."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM emails WHERE thread_id = ? AND user_email = ? ORDER BY date ASC", 
            (thread_id, user_email)
        )
        rows = cursor.fetchall()
        return [map_email_row(row) for row in rows]

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
                html_content TEXT,
                followup_count INTEGER DEFAULT 0,
                institute_name TEXT,
                user_email TEXT,
                last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migration: Add html_content if it doesn't exist
        try:
            cursor.execute("ALTER TABLE emails ADD COLUMN html_content TEXT")
        except sqlite3.OperationalError:
            pass # Already exists
        
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

def save_emails_batch(user_email: str, emails: List[Dict[str, Any]]):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO emails (
                id, gmail_id, thread_id, parent_email_id, sender, sender_email, 
                recipient_email, subject, content, category, mail_type, priority, 
                date, has_attachment, attachments, is_demo, replied, is_trashed, 
                is_inbox, is_sent, is_priority_refined, is_ocr_processed, 
                attachment_content, html_content, followup_count, institute_name, user_email
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                gmail_id=COALESCE(excluded.gmail_id, gmail_id),
                thread_id=COALESCE(excluded.thread_id, thread_id),
                parent_email_id=COALESCE(excluded.parent_email_id, parent_email_id),
                sender=COALESCE(excluded.sender, sender),
                sender_email=COALESCE(excluded.sender_email, sender_email),
                recipient_email=COALESCE(excluded.recipient_email, recipient_email),
                subject=COALESCE(excluded.subject, subject),
                content=COALESCE(excluded.content, content),
                category=CASE 
                    WHEN is_trashed=1 OR excluded.is_trashed=1 THEN 'trash' 
                    WHEN category IS NULL OR category = 'Sent' OR category = '' THEN excluded.category 
                    ELSE category 
                END,
                mail_type=COALESCE(excluded.mail_type, mail_type),
                priority=COALESCE(excluded.priority, priority),
                date=COALESCE(excluded.date, date),
                attachments=COALESCE(excluded.attachments, attachments),
                replied=MAX(replied, excluded.replied),
                is_trashed=MAX(is_trashed, excluded.is_trashed),
                is_inbox=MAX(is_inbox, excluded.is_inbox),
                is_sent=MAX(is_sent, excluded.is_sent),
                is_priority_refined=MAX(is_priority_refined, excluded.is_priority_refined),
                is_ocr_processed=MAX(is_ocr_processed, excluded.is_ocr_processed),
                attachment_content=COALESCE(excluded.attachment_content, attachment_content),
                html_content=COALESCE(excluded.html_content, html_content),
                followup_count=COALESCE(excluded.followup_count, followup_count),
                institute_name=COALESCE(excluded.institute_name, institute_name),
                last_synced=CURRENT_TIMESTAMP
        """

        # Category Normalization Map (from repair_categories.py)
        NORM_MAP = {
            "Examination / Semester": "Semester / Examination",
            "Misc": "Miscellaneous",
            "miscellaneous": "Miscellaneous",
            "Others": "Miscellaneous",
            "other": "Miscellaneous"
        }
        
        params = []
        for e in emails:
            # Apply Normalization
            cat = e.get("category", "Miscellaneous")
            cat = NORM_MAP.get(cat, cat)
            
            params.append((
                e['email_id'],
                e.get('gmail_id'),
                e.get('thread_id'),
                e.get('parent_email_id'),
                e.get('sender'),
                e.get('sender_email'),
                e.get('recipient_email'),
                e.get('subject'),
                e.get('content'),
                cat,
                str(e.get('mail_type') or 'fresh').lower(),
                e.get('priority', 6),
                e.get('date'),
                1 if e.get('has_attachment') else 0,
                json.dumps(e.get('attachments', [])),
                1 if e.get('is_demo') else 0,
                1 if e.get('replied') else 0,
                1 if e.get('is_trashed') else 0,
                1 if e.get('is_inbox') else 0,
                1 if e.get('is_sent') else 0,
                0, # is_priority_refined
                0, # is_ocr_processed
                None, # attachment_content
                e.get('html_content'),
                e.get('followup_count', 0),
                e.get('institute_name'),
                user_email
            ))

            cursor.execute(sql, params[-1])

        # Thread Reconciliation
        _reconcile_thread_replied_state(cursor, user_email, emails)
        conn.commit()

def _reconcile_thread_replied_state(cursor, user_email, emails):
    from utils.email_utils import normalize_email_address
    user_norm = normalize_email_address(user_email)
    
    tids = {e.get('thread_id') for e in emails if e.get('thread_id')}
    for tid in tids:
        # Relationship-Aware: Check the ABSOLUTE LATEST interaction in the thread
        cursor.execute("""
            SELECT is_sent, recipient_email FROM emails 
            WHERE thread_id = ? AND user_email = ? AND is_trashed = 0
            ORDER BY date DESC LIMIT 1
        """, (tid, user_email))
        latest = cursor.fetchone()
        
        if latest:
            is_sent, recipient_email = latest
            recipient_norm = normalize_email_address(recipient_email)
            
            # Rule: Only counts as 'Replied' if you sent to an EXTERNAL recipient.
            # You -> You tests do NOT resolve a citizen's grievance.
            is_replied_state = 1 if (is_sent and recipient_norm and recipient_norm != user_norm) else 0
            
            cursor.execute("UPDATE emails SET replied = ? WHERE thread_id = ? AND user_email = ?", (is_replied_state, tid, user_email))

def reconcile_user_thread_tags(user_email: str):
    """
    POST-SYNC RECONCILIATION:
    Standardizes tags (fresh, follow-up, reply) across all threads 
    to handle 'Batch Blindness' and ensure perfect history.
    """
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # Select all active thread IDs for this user
        cursor.execute(
            "SELECT DISTINCT thread_id FROM emails WHERE user_email = ? AND is_trashed = 0",
            (user_email,)
        )
        thread_ids = [r[0] for r in cursor.fetchall() if r[0]]
        
        from utils.email_utils import normalize_email_address
        user_norm = normalize_email_address(user_email)
        
        for tid in thread_ids:
            cursor.execute("""
                SELECT id, is_sent, sender_email, recipient_email FROM emails 
                WHERE thread_id = ? AND user_email = ? AND is_trashed = 0 
                ORDER BY date ASC
            """, (tid, user_email))
            msgs = cursor.fetchall()
            
            external_inbound_found = False
            follow_count = 0
            
            for msg in msgs:
                eid, is_sent, sender_email, recipient_email = msg
                s_norm = normalize_email_address(sender_email)
                r_norm = normalize_email_address(recipient_email)
                
                if is_sent:
                    if r_norm == user_norm:
                        # Self-Test: First one is 'fresh' (for testing), others are 'follow-up'
                        if not external_inbound_found and follow_count == 0:
                            new_type = 'fresh'
                        else:
                            new_type = 'follow-up'
                        follow_count += 1
                    elif not external_inbound_found:
                        # Proactive Ping
                        new_type = 'action'
                        # Note: We don't increment follow_count here typically for clean dashboard math
                    else:
                        # Response to a grievance
                        new_type = 'reply'
                        follow_count += 1
                else:
                    # Inbound Logic
                    if s_norm == user_norm:
                        # Inbound from Self (Legacy/Import path)
                        new_type = 'follow-up'
                        follow_count += 1
                    elif not external_inbound_found:
                        # FIRST EXTERNAL RESPONSE = FRESH
                        new_type = 'fresh'
                        external_inbound_found = True
                        follow_count = 0 # Reset for the new grievance anchor
                    else:
                        # Subsequent Inbound
                        new_type = 'follow-up'
                        follow_count += 1
                
                cursor.execute(
                    "UPDATE emails SET mail_type = ?, followup_count = ? WHERE id = ?",
                    (new_type, follow_count, eid)
                )
        
        conn.commit()

def get_emails_from_db(user_email: str, category: str = 'all', is_demo: Optional[bool] = None) -> List[Dict[str, Any]]:
    category_map = {
        'suspension': 'Suspension / Disciplinary', 'legal': 'Legal Issues', 'fir': 'Legal Issues',
        'rti': 'RTI Matters', 'cmo': 'CMO Issues', 'semester': 'Semester / Examination',
        'exam': 'Semester / Examination', 'scholarship': 'Scholarship & Fee Concession',
        'purchase': 'Purchase / Procurement Issues', 'cash': 'Cash Issues', 'ragging': 'Anti-Ragging Complaints',
        'accreditation': 'Accreditation & Ranking', 'service': 'Service Matters', 'appointment': 'Appointment Issues',
        'transfer': 'Transfer Cases', 'inspection': 'Inspection Matters', 'seat-matrix': 'Seat Matrix Issues',
        'miscellaneous': 'Miscellaneous'
    }
    db_category = category_map.get(category, category)
    
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM emails WHERE user_email = ?"
        params = [user_email]
        
        if category == 'trash':
            query += " AND is_trashed = 1"
        elif category == 'dashboard':
            query += " AND (is_inbox = 1 OR is_sent = 1) AND is_trashed = 0"
        elif category == 'all':
            query += " AND is_inbox = 1 AND is_trashed = 0"
        elif category == 'Sent':
            query += " AND is_sent = 1 AND is_trashed = 0"
        elif category == 'miscellaneous':
            main_categories = list(set(category_map.values()))
            placeholders = ', '.join(['?'] * len(main_categories))
            query += f" AND category NOT IN ({placeholders}) AND is_inbox = 1 AND is_trashed = 0"
            params.extend(main_categories)
        else:
            query += " AND category = ? AND is_inbox = 1 AND is_trashed = 0"
            params.append(db_category)
            
        if is_demo is not None:
            query += " AND is_demo = ?"
            params.append(1 if is_demo else 0)
            
        query += " ORDER BY priority ASC, date DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            email = dict(row)
            # Production Compatibility Transform (Aligning with api.ts Frontend Interfaces)
            email['email_id'] = email['id']
            email['hasAttachment'] = bool(email['has_attachment'])
            email['is_demo'] = bool(email['is_demo'])
            email['replied'] = bool(email['replied'])
            email['emailDate'] = email['date']
            email['parentEmailId'] = email.get('parent_email_id')
            email['mailType'] = email.get('mail_type')
            email['followUpCount'] = email.get('followup_count', 0)
            email['senderEmail'] = email.get('sender_email')
            email['instituteName'] = email.get('institute_name')
            email['emlFile'] = f"{email['id']}.eml"
            email['attachments'] = json.loads(email['attachments'] or '[]')
            result.append(email)
        return result

def get_thread_from_db(user_email: str, thread_id: str) -> List[Dict[str, Any]]:
    """Retrieves all emails in a conversation thread, sorted by date."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM emails 
            WHERE user_email = ? AND thread_id = ?
            ORDER BY date ASC
        """, (user_email, thread_id))
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            email = dict(row)
            # Standard Alignment (Same as get_emails_from_db)
            email['email_id'] = email['id']
            email['hasAttachment'] = bool(email['has_attachment'])
            email['is_demo'] = bool(email['is_demo'])
            email['replied'] = bool(email['replied'])
            email['emailDate'] = email['date']
            email['parentEmailId'] = email.get('parent_email_id')
            email['mailType'] = email.get('mail_type')
            email['followUpCount'] = email.get('followup_count', 0)
            email['senderEmail'] = email.get('sender_email')
            email['instituteName'] = email.get('institute_name')
            email['emlFile'] = f"{email['id']}.eml"
            email['attachments'] = json.loads(email['attachments'] or '[]')
            result.append(email)
        return result

def mark_as_trashed(user_email: str, email_id: str, is_trashed: bool = True):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if is_trashed:
            cursor.execute("UPDATE emails SET is_trashed = 1, category = 'trash' WHERE id = ? AND user_email = ?", (email_id, user_email))
        else:
            cursor.execute("UPDATE emails SET is_trashed = 0, is_inbox = 1, category = 'Miscellaneous' WHERE id = ? AND user_email = ?", (email_id, user_email))
        conn.commit()

def get_existing_gmail_ids(user_email: str) -> set:
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT gmail_id FROM emails WHERE user_email = ? AND gmail_id IS NOT NULL", (user_email,))
        return {row[0] for row in cursor.fetchall()}

def delete_all_for_user(user_email: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM emails WHERE user_email = ?", (user_email,))
        conn.commit()

def revoke_user_session(user_email: str, reason: str = 'Google Security Event'):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO revoked_sessions (user_email, reason) VALUES (?, ?)", (user_email.strip().lower(), reason))
        conn.commit()

def is_user_revoked(user_email: str) -> bool:
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM revoked_sessions WHERE user_email = ?", (user_email.strip().lower(),))
        return cursor.fetchone() is not None

def get_refinement_stats(user_email: str) -> Dict[str, int]:
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_priority_refined = 1 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        refined = cursor.fetchone()[0] or 0
        return {"refined": refined, "total": total}

def save_chat_message(user_email: str, session_id: str, role: str, message: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (user_email, session_id, role, message) VALUES (?, ?, ?, ?)", (user_email, session_id, role, message))
        conn.commit()

def get_chat_history(user_email: str, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, message FROM (
                SELECT role, message, timestamp FROM chat_history 
                WHERE user_email = ? AND session_id = ? 
                ORDER BY timestamp DESC LIMIT ?
            ) ORDER BY timestamp ASC
        """, (user_email, session_id, limit))
        return [dict(row) for row in cursor.fetchall()]

def touch_user_sync_time(user_email: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE emails SET last_synced = CURRENT_TIMESTAMP WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        conn.commit()

def get_user_sync_history(user_email: str) -> Optional[Dict[str, Any]]:
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_sync_history WHERE user_email = ?", (user_email,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_user_sync_history(user_email: str, history_id: str, reset_errors: bool = True):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        if reset_errors:
            cursor.execute("""
                INSERT INTO user_sync_history (user_email, last_history_id, last_sync_completed, consecutive_errors)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(user_email) DO UPDATE SET last_history_id = excluded.last_history_id, last_sync_completed = excluded.last_sync_completed, consecutive_errors = 0
            """, (user_email, history_id, now))
        else:
            cursor.execute("""
                INSERT INTO user_sync_history (user_email, last_history_id, last_sync_completed)
                VALUES (?, ?, ?)
                ON CONFLICT(user_email) DO UPDATE SET last_history_id = excluded.last_history_id, last_sync_completed = excluded.last_sync_completed
            """, (user_email, history_id, now))
        conn.commit()

def log_sync_audit(user_email: str, sync_type: str, status: str, duration_ms: int, added: int = 0, deleted: int = 0, error: str = None):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sync_audit (user_email, sync_type, status, duration_ms, messages_added, messages_deleted, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_email, sync_type, status, duration_ms, added, deleted, error))
        conn.commit()

def increment_sync_error(user_email: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE user_sync_history SET consecutive_errors = consecutive_errors + 1 WHERE user_email = ?", (user_email,))
        conn.commit()

def get_consecutive_sync_errors(user_email: str) -> int:
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT consecutive_errors FROM user_sync_history WHERE user_email = ?", (user_email,))
        row = cursor.fetchone()
        return row[0] if row else 0

def get_pending_ocr_emails(user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE user_email = ? AND has_attachment = 1 AND is_ocr_processed = 0 AND is_trashed = 0 LIMIT ?", (user_email, limit))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d['attachments'] = json.loads(d['attachments'] or '[]')
            result.append(d)
        return result

def update_email_attachment_content(user_email: str, email_id: str, text: str, filename: str = None, original_filename: str = None):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # 0. RESOLVE THREAD CONTEXT
        cursor.execute("SELECT thread_id FROM emails WHERE id = ?", (email_id,))
        thread_row = cursor.fetchone()
        thread_id = thread_row[0] if thread_row else None

        # 1. IDENTIFY TARGET ROWS
        # We target every email in the thread that specifically HOLDs this attachment.
        if thread_id:
            cursor.execute("""
                SELECT id, attachment_content FROM emails 
                WHERE thread_id = ? AND user_email = ?
                AND (attachments LIKE ? OR attachments LIKE ? OR id = ?)
            """, (thread_id, user_email, f'%{filename}%', f'%{original_filename}%', email_id))
        else:
            cursor.execute("SELECT id, attachment_content FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        
        target_rows = cursor.fetchall()

        # 2. TRANSACTIONAL PER-ROW SURGERY
        import re
        for r_id, r_content in target_rows:
            blocks = {}
            if r_content:
                # Split existing content into blocks by attachment header
                parts = r_content.split("--- [Extracted from Attachment: ")
                for part in parts:
                    if "]" in part:
                        fname_key, block_text = part.split("] ---", 1)
                        fname_key = fname_key.strip()
                        # Internal block deduplication
                        paras = [p.strip() for p in block_text.split("\n\n") if p.strip()]
                        seen_paras = []
                        for p in paras:
                            # Strip common lead-ins for comparison
                            clean_p = p.replace("Based on the image provided,", "").replace("The text in the image is as follows:", "").strip()
                            if clean_p and clean_p not in [sp.replace("Based on the image provided,", "").replace("The text in the image is as follows:", "").strip() for sp in seen_paras]:
                                seen_paras.append(p)
                        blocks[fname_key] = "\n\n".join(seen_paras)

            # 3. IDENTITY NORMALIZATION & PURGE (Per Row)
            def normalize_name(s):
                if not s: return ""
                return re.sub(r'[^a-z0-9]', '', s.lower())

            keys_to_delete = []
            target_norm = normalize_name(filename)
            orig_norm = normalize_name(original_filename) if original_filename else None
            # Fuzzy base: e.g. '5d0f47d2_Image.jpg' -> normalized 'imagejpg'
            target_base_norm = normalize_name(filename.split('_', 1)[1]) if '_' in filename else target_norm
            
            for k in list(blocks.keys()):
                k_norm = normalize_name(k)
                if k_norm == target_norm or (orig_norm and k_norm == orig_norm) or (k_norm and target_base_norm and (k_norm in target_base_norm or target_base_norm in k_norm)):
                    keys_to_delete.append(k)
            
            for k in set(keys_to_delete):
                if k in blocks: del blocks[k]

            # 4. FRESH INSERTION (Atomic for this row)
            # We use the 'filename' provided in metadata as the stable key
            blocks[filename or "attachment"] = text.strip()
            
            new_content_parts = []
            for fname, b_text in blocks.items():
                new_content_parts.append(f"--- [Extracted from Attachment: {fname}] ---\n{b_text}")
            
            serialized_content = "\n\n".join(new_content_parts)

            # 5. COMMIT ROW
            cursor.execute("""
                UPDATE emails 
                SET attachment_content = ?, is_ocr_processed = 1, last_synced = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (serialized_content, r_id))

        # 3. GLOBAL POLLUTION CLEANUP (Wipe rows with no attachments)
        if thread_id:
            cursor.execute("""
                UPDATE emails 
                SET attachment_content = NULL 
                WHERE thread_id = ? AND user_email = ? 
                AND (has_attachment = 0 OR attachments IS NULL OR attachments = '[]' OR attachments = '' OR length(attachments) < 3)
            """, (thread_id, user_email))
            
        conn.commit()

def get_unrefined_emails(user_email: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Returns a batch of emails that need AI priority/category refinement."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender, subject, content, attachment_content 
            FROM emails 
            WHERE user_email = ? 
              AND is_priority_refined = 0 
              AND is_trashed = 0 
              AND (has_attachment = 0 OR is_ocr_processed = 1)
            ORDER BY date DESC LIMIT ?
        """, (user_email, limit))
        return [dict(row) for row in cursor.fetchall()]

def update_email_refinement(user_email: str, email_id: str, priority: int, category: str):
    """Updates an email with AI-refined priority and category labels with casing safety."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails 
            SET priority = ?, category = ?, is_priority_refined = 1, last_synced = CURRENT_TIMESTAMP 
            WHERE id = ? AND LOWER(user_email) = LOWER(?)
        """, (priority, category, email_id, user_email.strip()))
        conn.commit()
        return cursor.rowcount

def reset_refinement_status(user_email: str, email_id: str):
    """Resets the refinement flag to trigger a fresh AI triage run."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails SET is_priority_refined = 0, last_synced = CURRENT_TIMESTAMP
            WHERE id = ? AND user_email = ?
        """, (email_id, user_email))
        conn.commit()

def get_unprocessed_attachments(user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Returns attachments that exist locally but haven't been OCR-processed yet."""
    import json
    from config import ATTACHMENTS_DIR
    
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id as email_id, attachments 
            FROM emails 
            WHERE user_email = ? AND has_attachment = 1 AND is_ocr_processed = 0 AND is_trashed = 0 
            LIMIT ?
        """, (user_email, limit))
        results = []
        for row in cursor.fetchall():
            try:
                atts = json.loads(row['attachments'] or '[]')
                for att in atts:
                    filename = None
                    # Handle both new Dict format and legacy String format
                    if isinstance(att, dict):
                        filename = att.get('filename')
                    elif isinstance(att, str):
                        filename = att
                        
                    if filename:
                        # 1. Direct Hit Check
                        path = ATTACHMENTS_DIR / filename
                        if path.exists():
                            results.append({
                                "email_id": row['email_id'],
                                "filename": filename,
                                "original_name": att.get('original_name') if isinstance(att, dict) else filename,
                                "local_path": str(path.absolute())
                            })
                        else:
                            # 2. Fuzzy Recovery: Look for {any_prefix}_{filename}
                            # Useful for legacy data where the DB only has the original name
                            safe_name = filename.replace(" ", "_").replace("/", "_")
                            for candidate in ATTACHMENTS_DIR.glob(f"*_{safe_name}"):
                                results.append({
                                    "email_id": row['email_id'],
                                    "filename": candidate.name,
                                    "original_name": filename, # In this case, filename was the original name
                                    "local_path": str(candidate.absolute())
                                })
                                break # Found it
            except Exception as e:
                print(f"⚠️ Error parsing attachment metadata for {row['email_id']}: {e}")
                
        return results

def has_enrichment_work(user_email: str) -> bool:
    """Returns True if there are any emails waiting for OCR or AI refinement."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Check for OCR backlog
        cursor.execute("SELECT 1 FROM emails WHERE user_email = ? AND has_attachment = 1 AND is_ocr_processed = 0 AND is_trashed = 0 LIMIT 1", (user_email,))
        if cursor.fetchone(): return True
        # Check for AI Refinement backlog
        cursor.execute("SELECT 1 FROM emails WHERE user_email = ? AND is_priority_refined = 0 AND is_trashed = 0 AND (has_attachment = 0 OR is_ocr_processed = 1) LIMIT 1", (user_email,))
        if cursor.fetchone(): return True
        return False

def update_email_labels_locally(user_email: str, gmail_id: str, is_trashed: bool):
    """Updates flags when server-side labels change (e.g., deleted in Gmail App)."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if is_trashed:
            cursor.execute("""
                UPDATE emails 
                SET is_trashed = 1, is_inbox = 0, category = 'trash', last_synced = CURRENT_TIMESTAMP 
                WHERE gmail_id = ? AND user_email = ?
            """, (gmail_id, user_email))
        else:
            cursor.execute("""
                UPDATE emails 
                SET is_trashed = 0, is_inbox = 1, category = 'Miscellaneous', last_synced = CURRENT_TIMESTAMP 
                WHERE gmail_id = ? AND user_email = ?
            """, (gmail_id, user_email))
        conn.commit()

def update_sync_interval(user_email: str, seconds: int):
    """Updates the user's synchronization frequency preference and marks the override timestamp."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_sync_history 
                (user_email, sync_interval_seconds, interval_updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_email) DO UPDATE SET 
                sync_interval_seconds = excluded.sync_interval_seconds,
                interval_updated_at = CURRENT_TIMESTAMP
        """, (user_email, seconds))
        conn.commit()
def get_categories_from_db(user_email: str) -> List[Dict[str, Any]]:
    """Retrieves grievance categories and their respective counts for the filter sidebar."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Only count items in Inbox (not Send, not Trash)
        cursor.execute("""
            SELECT category as name, COUNT(*) as count 
            FROM emails 
            WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0
            GROUP BY category
        """, (user_email,))
        return [dict(row) for row in cursor.fetchall()]

def get_dashboard_stats(user_email: str) -> Dict[str, int]:
    """Retrieves high-level summary counts for the dashboard header."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # Total active grievances
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
        total = cursor.fetchone()[0] or 0
        
        # Fresh (not yet refined by AI)
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 AND is_priority_refined = 0", (user_email,))
        fresh = cursor.fetchone()[0] or 0
        
        # Followups (Detected by thread depth)
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 AND followup_count > 0", (user_email,))
        followup = cursor.fetchone()[0] or 0
        
        return {
            "total": total,
            "fresh": fresh,
            "followup": followup
        }

def get_all_active_users() -> List[str]:
    """Retrieves all distinct user emails that have been registered/synced."""
    from db.session import get_db_conn
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_email FROM user_sync_history")
        return [row[0] for row in cursor.fetchall()]
