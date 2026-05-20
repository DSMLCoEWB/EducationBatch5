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
        
def toggle_resolution_status(user_email: str, email_id: str, is_resolved: bool = True):
    """Toggle the manual resolution status for an entire thread."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Find thread_id first
        cursor.execute("SELECT thread_id FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        row = cursor.fetchone()
        thread_id = row[0] if row else None
        
        val = 1 if is_resolved else 0
        if thread_id:
            cursor.execute(
                "UPDATE emails SET is_resolved = ?, manual_override = 1 WHERE thread_id = ? AND user_email = ?", 
                (val, thread_id, user_email)
            )
        else:
            cursor.execute(
                "UPDATE emails SET is_resolved = ?, manual_override = 1 WHERE id = ? AND user_email = ?", 
                (val, email_id, user_email)
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
    email['to']             = email.get('to_address')
    email['cc']             = email.get('cc_address')
    email['bcc']            = email.get('bcc_address')
    
    email['hasAttachment'] = bool(email.get('has_attachment'))
    email['is_demo']       = bool(email.get('is_demo'))
    email['replied']       = bool(email.get('replied'))
    email['is_resolved']   = bool(email.get('is_resolved'))
    email['manual_override'] = bool(email.get('manual_override'))
    
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
                is_resolved BOOLEAN DEFAULT 0,
                manual_override BOOLEAN DEFAULT 0,
                to_address TEXT,
                cc_address TEXT,
                bcc_address TEXT,
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_view_opt ON emails (user_email, is_inbox, is_trashed, date DESC)")

        # Create Unified Grievance View (Synchronized with Dashboard.tsx logic)
        cursor.execute("DROP VIEW IF EXISTS v_threads")
        cursor.execute("""
            CREATE VIEW v_threads AS
            WITH            abs_latest AS (
                SELECT thread_id, replied, is_resolved, manual_override, mail_type, date, user_email, category, priority, subject, institute_name, has_attachment, content, is_trashed,
                       ROW_NUMBER() OVER (PARTITION BY user_email, thread_id, is_trashed ORDER BY date DESC) as rn
                FROM emails
                WHERE is_inbox = 1
            ),
            citizen_latest AS (
                SELECT thread_id, mail_type, user_email, category, priority, subject, institute_name, content, is_trashed,
                       ROW_NUMBER() OVER (PARTITION BY user_email, thread_id, is_trashed ORDER BY date DESC) as rn
                FROM emails
                WHERE is_inbox = 1 AND is_sent = 0
            ),
            thread_state AS (
                SELECT 
                    a.thread_id, a.user_email, a.replied, a.is_resolved, a.manual_override, a.is_trashed,
                    COALESCE(c.mail_type, a.mail_type) as mail_type,
                    COALESCE(c.category, a.category) as category,
                    COALESCE(c.priority, a.priority) as priority,
                    COALESCE(c.subject, a.subject) as subject,
                    COALESCE(c.institute_name, a.institute_name) as institute_name,
                    COALESCE(c.content, a.content) as content,
                    a.has_attachment,
                    a.date as last_message_date,
                    CASE 
                        WHEN (a.manual_override = 1 AND a.is_resolved = 1) 
                          OR (COALESCE(a.manual_override, 0) = 0 AND (a.replied = 1 OR a.is_resolved = 1)) 
                        THEN 'resolved'
                        WHEN COALESCE(c.mail_type, a.mail_type) = 'fresh' THEN 'fresh'
                        ELSE 'ongoing'
                    END as status
                FROM abs_latest a
                LEFT JOIN citizen_latest c ON a.thread_id = c.thread_id AND a.user_email = c.user_email AND a.is_trashed = c.is_trashed AND c.rn = 1
                WHERE a.rn = 1
            )
            SELECT * FROM thread_state
        """)

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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                name TEXT,
                color TEXT,
                icon TEXT DEFAULT 'Hash',
                is_active BOOLEAN DEFAULT 1,
                user_email TEXT,
                UNIQUE(user_email, name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS priority_rules (
                priority INTEGER,
                user_email TEXT,
                label TEXT,
                keywords TEXT,
                description TEXT DEFAULT '',
                PRIMARY KEY (user_email, priority)
            )
        """)

        # NOTE: Category seeding is now handled per-user in ensure_user_categories()

        
        # [SELF-HEALING]: Ensure 'has_attachment' is correctly set
        cursor.execute("""
            UPDATE emails 
            SET has_attachment = 1 
            WHERE (has_attachment = 0 OR has_attachment IS NULL) 
              AND (attachments IS NOT NULL AND attachments != '[]')
        """)

        # Migration logic (Ensure columns exist)
        _run_migrations(cursor)
        
        # [SELF-HEALING]: Thread-Aware Resolution Backfill
        # Only marks a thread as Resolved if there is a 'Sent' message to an EXTERNAL recipient.
        cursor.execute("""
            UPDATE emails 
            SET replied = 1, is_resolved = 1 
            WHERE thread_id IN (
                SELECT DISTINCT thread_id FROM emails 
                WHERE is_sent = 1 AND is_trashed = 0 
                AND recipient_email != user_email
            )
            AND (replied = 0 OR is_resolved = 0)
            AND manual_override = 0
        """)

        # [CORRECTION]: Undo incorrect resolutions for threads that only contain self-sent interactions
        cursor.execute("""
            UPDATE emails 
            SET replied = 0, is_resolved = 0 
            WHERE thread_id NOT IN (
                SELECT DISTINCT thread_id FROM emails 
                WHERE is_sent = 1 AND is_trashed = 0 AND recipient_email != user_email
            )
            AND (replied = 1 OR is_resolved = 1)
            AND manual_override = 0
        """)
        
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
        "is_resolved": "BOOLEAN DEFAULT 0",
        "manual_override": "BOOLEAN DEFAULT 0",
        "to_address": "TEXT",
        "cc_address": "TEXT",
        "bcc_address": "TEXT",
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

    # Migrate categories table
    try:
        cursor.execute("SELECT icon FROM categories LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB Migration] Adding icon column to categories...")
        cursor.execute("ALTER TABLE categories ADD COLUMN icon TEXT DEFAULT 'Hash'")

    # Migrate priority_rules table to support dynamic description rubrics
    try:
        cursor.execute("SELECT description FROM priority_rules LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB Migration] Adding description column to priority_rules...")
        try:
            cursor.execute("ALTER TABLE priority_rules ADD COLUMN description TEXT DEFAULT ''")
        except Exception as e:
            print(f"[DB Migration] Warning: Failed to alter priority_rules: {e}")

    # Create system metadata table to track one-time migrations and tasks
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        cursor.execute("SELECT value FROM system_metadata WHERE key = 'priority_rubrics_backfilled'")
        row = cursor.fetchone()
        has_desc_seeded = row is not None and row[0] == 'true'
        
        if not has_desc_seeded:
            print("[DB Migration] Seeding default descriptions for priority rules...")
            default_descs = {
                0: "Chief Secretary / Cabinet / Highest Government Authority (Mandatory Command), Court orders, RTI Matters, Examination Paper Leakage/Breach, Major Student Accidents (Critical)",
                1: "Anti-Ragging Complaints, FIR cases, CMO Issues, Ministerial References, Service Matters (Salary/Pension Delays), Suspensions / Disciplinary, Financial Fraud (High Stakes & Integrity)",
                2: "Tenders / Procurement (Deadlines), Seat Matrix, Accreditation (NAAC/NBA), Ordinary Leave Requests, Admissions, Semester / Examination routine, Scholarship Queries (Routine & Medium Stakes)",
                3: "Miscellaneous, routine queries, website feedback, or general information (Standard/Low)"
            }
            for prio, desc in default_descs.items():
                cursor.execute("UPDATE priority_rules SET description = ? WHERE priority = ? AND (description = '' OR description IS NULL)", (desc, prio))
            
            cursor.execute("INSERT OR REPLACE INTO system_metadata (key, value) VALUES ('priority_rubrics_backfilled', 'true')")
    except Exception as e:
        print(f"[DB Migration] Warning: Failed to backfill descriptions: {e}")

def save_emails_batch(user_email: str, emails: List[Dict[str, Any]]):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO emails (
                id, gmail_id, thread_id, parent_email_id, sender, sender_email, 
                recipient_email, subject, content, category, mail_type, priority, 
                date, has_attachment, attachments, is_demo, replied, is_trashed, 
                is_inbox, is_sent, is_priority_refined, is_ocr_processed, 
                attachment_content, html_content, followup_count, institute_name, 
                to_address, cc_address, bcc_address, user_email
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                priority=CASE 
                    WHEN is_priority_refined=1 THEN priority 
                    ELSE excluded.priority 
                END,
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
                to_address=COALESCE(excluded.to_address, to_address),
                cc_address=COALESCE(excluded.cc_address, cc_address),
                bcc_address=COALESCE(excluded.bcc_address, bcc_address),
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
                1 if e.get('is_priority_refined') else 0,
                1 if e.get('is_ocr_processed') else 0,
                e.get('attachment_content'), # attachment_content
                e.get('html_content'),
                e.get('followup_count', 0),
                e.get('institute_name'),
                e.get('to'),
                e.get('cc'),
                e.get('bcc'),
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
        # 1. Get manual override state
        cursor.execute("""
            SELECT MAX(manual_override) FROM emails 
            WHERE thread_id = ? AND user_email = ?
        """, (tid, user_email))
        is_locked = bool(cursor.fetchone()[0])

        # 2. Check if the thread has ANY external reply (marks it as potentially resolved)
        cursor.execute("""
            SELECT COUNT(*) FROM emails 
            WHERE thread_id = ? AND user_email = ? AND is_sent = 1 AND is_trashed = 0
            AND recipient_email != user_email
        """, (tid, user_email))
        has_external_reply = cursor.fetchone()[0] > 0
        
        # 3. Check for new citizen inbounds AFTER the last external reply
        new_inbounds = 0
        if has_external_reply:
            cursor.execute("""
                SELECT MAX(date) FROM emails 
                WHERE thread_id = ? AND user_email = ? AND is_sent = 1 AND is_trashed = 0
                AND recipient_email != user_email
            """, (tid, user_email))
            last_reply_date = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) FROM emails 
                WHERE thread_id = ? AND user_email = ? AND is_sent = 0 AND is_trashed = 0
                AND date > ?
            """, (tid, user_email, last_reply_date))
            new_inbounds = cursor.fetchone()[0]
            
        # 4. SMART RESET LOGIC & APPLY STATE
        if has_external_reply and new_inbounds > 0:
            # NEW INBOUND: Reset lock and reopen grievance
            cursor.execute(
                "UPDATE emails SET replied = 0, is_resolved = 0, manual_override = 0 WHERE thread_id = ? AND user_email = ?", 
                (tid, user_email)
            )
        elif not is_locked:
            # NO LOCK: Apply automated logic
            is_replied_state = 1 if has_external_reply else 0
            cursor.execute(
                "UPDATE emails SET replied = ?, is_resolved = ? WHERE thread_id = ? AND user_email = ?", 
                (is_replied_state, is_replied_state, tid, user_email)
            )
        # If is_locked and no new inbounds: DO NOTHING (respect manual override)


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
                WHERE thread_id = ? AND user_email = ?
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
                    "UPDATE emails SET mail_type = ?, followup_count = ? WHERE id = ? AND user_email = ?",
                    (new_type, follow_count, eid, user_email)
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
            email['is_resolved'] = bool(email['is_resolved'])
            email['manual_override'] = bool(email.get('manual_override'))
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
    """Retrieves all emails in a conversation thread, sorted by date.
    Matches Gmail behavior: trashed messages are hidden but available for 'View message'."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM emails 
            WHERE user_email = ? AND thread_id = ?
            ORDER BY date ASC
        """, (user_email, thread_id))
        rows = cursor.fetchall()
        
        deleted_count = sum(1 for row in rows if row['is_trashed'])
        
        result = []
        for row in rows:
            email = dict(row)
            # Standard Alignment (Same as get_emails_from_db)
            email['email_id'] = email['id']
            email['hasAttachment'] = bool(email['has_attachment'])
            email['is_demo'] = bool(email['is_demo'])
            email['replied'] = bool(email['replied'])
            email['is_resolved'] = bool(email['is_resolved'])
            email['manual_override'] = bool(email.get('manual_override'))
            email['emailDate'] = email['date']
            email['parentEmailId'] = email.get('parent_email_id')
            email['mailType'] = email.get('mail_type')
            email['followUpCount'] = email.get('followup_count', 0)
            email['senderEmail'] = email.get('sender_email')
            email['instituteName'] = email.get('institute_name')
            email['emlFile'] = f"{email['id']}.eml"
            email['attachments'] = json.loads(email['attachments'] or '[]')
            email['deleted_in_thread'] = deleted_count
            email['is_trashed_msg'] = bool(email.get('is_trashed'))
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
    """Returns AI refinement coverage statistics (Email-level precision)."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Count individual messages for higher precision
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
    from config import AI_PREFER_LOCAL
    # Restrict Gemini API from processing the heavy demo batch
    demo_filter = "" if AI_PREFER_LOCAL else "AND is_demo = 0"
    
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT id, sender, subject, content, attachment_content 
            FROM emails 
            WHERE user_email = ? 
              AND is_priority_refined = 0 
              AND is_trashed = 0 
              AND (has_attachment = 0 OR is_ocr_processed = 1)
              {demo_filter}
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
            WHERE id = ? AND LOWER(user_email) = LOWER(?) AND is_demo = 0
        """, (priority, category, email_id, user_email.strip()))
        conn.commit()
        return cursor.rowcount

def reset_refinement_status(user_email: str, email_id: str):
    """Resets the refinement status of an email to trigger AI re-processing."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails 
            SET is_priority_refined = 0 
            WHERE id = ? AND user_email = ? AND is_demo = 0
        """, (email_id, user_email))
        conn.commit()
        return cursor.rowcount

def get_active_categories(user_email: str):
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, color, icon FROM categories WHERE is_active = 1 AND user_email = ?", (user_email,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_categories(user_email: str):
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, color, icon, is_active FROM categories WHERE user_email = ?", (user_email,))
        return [dict(row) for row in cursor.fetchall()]

def add_category(user_email: str, name: str, color: str, icon: str):
    import uuid
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_active FROM categories WHERE name = ? AND user_email = ?", (name, user_email))
        row = cursor.fetchone()
        if row:
            if not row[1]: 
                cursor.execute("UPDATE categories SET is_active = 1, color = ?, icon = ? WHERE id = ?", (color, icon, row[0]))
                cursor.execute("UPDATE emails SET is_priority_refined = 0 WHERE user_email = ? AND is_demo = 0", (user_email,))
                conn.commit()
                return row[0]
            else:
                raise ValueError("Category already exists.")
        
        new_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO categories (id, name, color, icon, is_active, user_email) VALUES (?, ?, ?, ?, 1, ?)", (new_id, name, color, icon, user_email))
        cursor.execute("UPDATE emails SET is_priority_refined = 0 WHERE user_email = ? AND is_demo = 0", (user_email,))
        conn.commit()
        return new_id

def update_category(user_email: str, cat_id: str, name: str, color: str, icon: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Fetch current name to see if it actually changed
        cursor.execute("SELECT name FROM categories WHERE id = ? AND user_email = ?", (cat_id, user_email))
        row = cursor.fetchone()
        old_name = row[0] if row else None
        
        cursor.execute("UPDATE categories SET name = ?, color = ?, icon = ? WHERE id = ? AND user_email = ?", (name, color, icon, cat_id, user_email))
        
        # Only reset refinement and migrate emails if the semantic name changed
        if old_name and old_name.lower() != name.lower():
            # 1. Migrate existing emails to the new name immediately
            cursor.execute("UPDATE emails SET category = ? WHERE category = ? AND user_email = ?", (name, old_name, user_email))
            # 2. Reset refinement so AI can double-check the logic
            cursor.execute("UPDATE emails SET is_priority_refined = 0 WHERE user_email = ? AND is_demo = 0", (user_email,))
            
        conn.commit()

def delete_category(user_email: str, cat_id: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories WHERE id = ? AND user_email = ?", (cat_id, user_email))
        row = cursor.fetchone()
        if not row:
            return
        cat_name = row[0]
        
        cursor.execute("UPDATE categories SET is_active = 0 WHERE id = ? AND user_email = ?", (cat_id, user_email))
        
        cursor.execute("""
            UPDATE emails 
            SET category = 'Miscellaneous', 
                is_priority_refined = (CASE WHEN is_demo = 1 THEN is_priority_refined ELSE 0 END)
            WHERE category = ? AND user_email = ?
        """, (cat_name, user_email))
        conn.commit()

def ensure_user_categories(user_email: str):
    """Provisions default administrative categories for a new user if none exist."""
    from core.logging import get_logger
    logger = get_logger("db.repository")
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM categories WHERE user_email = ?", (user_email,))
        if cursor.fetchone()[0] == 0:
            logger.info(f"🌱 Provisioning default categories for {user_email}")
            default_categories = [
                ("Suspension / Disciplinary", "hsl(25, 95%, 53%)", "Gavel"),
                ("Legal Issues", "hsl(0, 72%, 51%)", "Scale"),
                ("RTI Matters", "hsl(210, 100%, 50%)", "FileSearch"),
                ("CMO Issues", "hsl(260, 100%, 50%)", "Building"),
                ("Semester / Examination", "hsl(234, 89%, 54%)", "ClipboardList"),
                ("Scholarship & Fee Concession", "hsl(40, 95%, 38%)", "GraduationCap"),
                ("Purchase / Procurement Issues", "hsl(160, 100%, 40%)", "ShoppingCart"),
                ("Cash Issues", "hsl(340, 80%, 50%)", "Banknote"),
                ("Anti-Ragging Complaints", "hsl(15, 90%, 50%)", "ShieldAlert"),
                ("Accreditation & Ranking", "hsl(280, 100%, 60%)", "Award"),
                ("Service Matters", "hsl(180, 100%, 40%)", "Briefcase"),
                ("Appointment Issues", "hsl(130, 70%, 45%)", "UserPlus"),
                ("Transfer Cases", "hsl(200, 90%, 45%)", "ArrowLeftRight"),
                ("Inspection Matters", "hsl(250, 80%, 55%)", "Search"),
                ("Seat Matrix Issues", "hsl(310, 80%, 50%)", "Table"),
                ("Miscellaneous", "hsl(0, 0%, 45%)", "Archive")
            ]
            import uuid
            for cat_name, cat_color, cat_icon in default_categories:
                try:
                    cursor.execute(
                        "INSERT INTO categories (id, name, color, icon, is_active, user_email) VALUES (?, ?, ?, ?, 1, ?)",
                        (str(uuid.uuid4()), cat_name, cat_color, cat_icon, user_email)
                    )
                except: pass # Race condition safety
            conn.commit()

def get_priority_rules(user_email: str) -> List[Dict[str, Any]]:
    """Fetches custom priority rules for a specific user. Seeds default keywords and descriptions self-healingly if empty."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT priority, label, keywords, description FROM priority_rules WHERE user_email = ? AND priority >= 0 ORDER BY priority ASC", (user_email,))
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            cursor.execute("SELECT priority, label, keywords FROM priority_rules WHERE user_email = ? AND priority >= 0 ORDER BY priority ASC", (user_email,))
            rows = cursor.fetchall()
        
        if not rows:
            # Seed default 4-level system keywords and dynamic description rubrics
            default_rules = [
                (0, "Critical", ["urgent", "critical", "cmo", "emergency", "immediate", "legal", "court", "salary", "pension", "arrear", "fixation", "seniority"], 
                 "Chief Secretary / Cabinet / Highest Government Authority (Mandatory Command), Court orders, RTI Matters, Examination Paper Leakage/Breach, Major Student Accidents (Critical)"),
                (1, "High", ["suspension", "disciplinary", "chargesheet", "misconduct", "ragging", "anti-ragging", "anti ragging", "transfer", "posting", "deputation"], 
                 "Anti-Ragging Complaints, FIR cases, CMO Issues, Ministerial References, Service Matters (Salary/Pension Delays), Suspensions / Disciplinary, Financial Fraud (High Stakes & Integrity)"),
                (2, "Medium", ["exam", "semester", "result", "marksheet", "admit", "scholarship", "svmcm", "oasis", "fee"], 
                 "Tenders / Procurement (Deadlines), Seat Matrix, Accreditation (NAAC/NBA), Ordinary Leave Requests, Admissions, Semester / Examination routine, Scholarship Queries (Routine & Medium Stakes)"),
                (3, "Low", ["general", "query", "status", "acknowledge"], 
                 "Miscellaneous, routine queries, website feedback, or general information (Standard/Low)")
            ]
            for prio, label, kw_list, desc in default_rules:
                cursor.execute(
                    "INSERT OR REPLACE INTO priority_rules (priority, user_email, label, keywords, description) VALUES (?, ?, ?, ?, ?)",
                    (prio, user_email, label, json.dumps(kw_list), desc)
                )
            conn.commit()
            
            # Re-fetch
            cursor.execute("SELECT priority, label, keywords, description FROM priority_rules WHERE user_email = ? AND priority >= 0 ORDER BY priority ASC", (user_email,))
            rows = cursor.fetchall()
            
        result = []
        for r in rows:
            try:
                kw = json.loads(r["keywords"])
            except:
                kw = []
            
            desc = ""
            if "description" in r.keys():
                desc = r["description"] or ""
                
            result.append({
                "priority": r["priority"],
                "label": r["label"],
                "keywords": kw,
                "description": desc
            })
        return result

def save_priority_rules(user_email: str, rules: List[Dict[str, Any]]):
    """Saves the user's custom priority rules (keywords and descriptions) and resets priority refinement for background re-triage."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        for r in rules:
            prio = int(r["priority"])
            label = str(r["label"])
            keywords = json.dumps(r["keywords"])
            description = str(r.get("description", ""))
            cursor.execute(
                "INSERT OR REPLACE INTO priority_rules (priority, user_email, label, keywords, description) VALUES (?, ?, ?, ?, ?)",
                (prio, user_email, label, keywords, description)
            )
        # Reset is_priority_refined = 0 on all non-demo emails to trigger recalculation with new rules!
        cursor.execute("UPDATE emails SET is_priority_refined = 0 WHERE user_email = ? AND is_demo = 0", (user_email,))
        conn.commit()

def get_global_rules(user_email: str) -> str:
    """Fetches custom global rules for a specific user. Seeds default if empty."""
    old_default = (
        "- Increase urgency (lower number), capped at Level 1, if ANY of the following are detected:\n"
        "  (a) User frustration, anger, or emotionally distressed tone or a truly urgent or time-sensitive matter.\n"
        "  (b) Excessive unanswered follow-ups (>3 follow-ups without resolution) or evidence of a significantly delayed departmental response.\n"
        "- Level 0 is reserved for Chief Secretary commands, court orders, major student accidents, and institutional breaches.\n"
        "- Anti-Ragging complaints and student safety grievances MUST follow Level 1 unless they involve a major medical emergency/accident."
    )
    
    new_default = (
        "- Increase urgency (lower number), capped at Level 1, if ANY of the following are detected:\n"
        "  (a) User frustration, anger, or emotionally distressed tone or a truly urgent or time-sensitive matter.\n"
        "  (b) Excessive unanswered follow-ups (>3 follow-ups without resolution) or evidence of a significantly delayed departmental response.\n"
        "- Level 0 is reserved for Chief Secretary commands, court orders, major student accidents, and institutional breaches.\n"
        "- Anti-Ragging complaints and student safety grievances MUST follow Level 1 unless they involve a major medical emergency/accident.\n"
        '- DO NOT classify general student "inquiries" or "enquiries" as Suspension/Disciplinary unless there is explicit mention of misconduct or penalties.\n'
        '- "SVMCMS", "Oasis", and "K3" are strictly Scholarship & Fee Concession matters.'
    )

    with get_db_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT description FROM priority_rules WHERE user_email = ? AND priority = -1",
                (user_email,)
            )
            row = cursor.fetchone()
            if row:
                current_val = row[0] or ""
                if current_val.strip() == old_default.strip():
                    cursor.execute(
                        "UPDATE priority_rules SET description = ? WHERE user_email = ? AND priority = -1",
                        (new_default, user_email)
                    )
                    conn.commit()
                    return new_default
                return current_val
        except sqlite3.OperationalError:
            pass

        # Seed default if not found
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO priority_rules (priority, user_email, label, keywords, description) VALUES (-1, ?, 'Global Rules', '[]', ?)",
                (user_email, new_default)
            )
            conn.commit()
        except Exception as e:
            print(f"[DB] Error seeding global rules: {e}")
            
        return new_default

def save_global_rules(user_email: str, global_rules: str):
    """Saves the user's custom global rules and resets priority refinement for re-triage."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO priority_rules (priority, user_email, label, keywords, description) VALUES (-1, ?, 'Global Rules', '[]', ?)",
            (user_email, global_rules)
        )
        # Reset is_priority_refined = 0 on all non-demo emails to trigger recalculation with new global rules!
        cursor.execute("UPDATE emails SET is_priority_refined = 0 WHERE user_email = ? AND is_demo = 0", (user_email,))
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
                            # Use recursive glob to find in user subdirectories
                            safe_name = filename.replace(" ", "_").replace("/", "_")
                            for candidate in ATTACHMENTS_DIR.glob(f"**/*_{safe_name}"):
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
        
        # Unresolved (manual or automated)
        cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0 AND replied = 0 AND is_resolved = 0", (user_email,))
        unresolved = cursor.fetchone()[0] or 0
        
        return {
            "total": total,
            "fresh": fresh,
            "followup": followup,
            "unresolved": unresolved
        }

def get_all_active_users() -> List[str]:
    """Retrieves all distinct user emails that have been registered/synced."""
    from db.session import get_db_conn
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_email FROM user_sync_history")
        return [row[0] for row in cursor.fetchall()]

def permanently_delete_email_locally(user_email: str, gmail_id: str):
    """Deletes an email record from the local database when it's permanently removed from Gmail."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM emails WHERE gmail_id = ? AND user_email = ?", (gmail_id, user_email))
        conn.commit()

def get_gmail_ids_by_status(user_email: str, is_trashed: bool) -> List[str]:
    """Returns all Gmail IDs in the local DB for a specific trash status."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        val = 1 if is_trashed else 0
        cursor.execute("SELECT gmail_id FROM emails WHERE user_email = ? AND is_trashed = ?", (user_email, val))
        return [row[0] for row in cursor.fetchall() if row[0]]

def auto_purge_stale_trash(user_email: str, days: int = 30) -> int:
    """Permanently removes emails from local DB that have been in Trash for more than X days."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Gmail date format is ISO or similar; we calculate the cutoff
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            DELETE FROM emails 
            WHERE user_email = ? AND is_trashed = 1 AND date < ?
        """, (user_email, cutoff))
        deleted = cursor.rowcount
        conn.commit()
        return deleted
