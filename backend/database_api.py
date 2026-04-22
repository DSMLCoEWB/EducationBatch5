import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grievances.db")

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    
    # Create an index for last_synced to speed up audit queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_last_synced ON emails(last_synced)")
    
    # [SELF-HEALING]: Ensure 'has_attachment' is correctly set for existing rows
    # This recovers emails with attachments that might have missed the flag during ingestion.
    cursor.execute("""
        UPDATE emails 
        SET has_attachment = 1 
        WHERE (has_attachment = 0 OR has_attachment IS NULL) 
          AND (attachments IS NOT NULL AND attachments != '[]')
    """)
    
    # Create the revoked_sessions table for Google RISC security notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revoked_sessions (
            user_email TEXT PRIMARY KEY,
            revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
    """)

    # Create chat_history table for conversational memory
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
    
    # [MIGRATION]: Add parent_email_id if it doesn't exist
    try:
        cursor.execute("SELECT parent_email_id FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("Database Migration: Adding parent_email_id column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN parent_email_id TEXT")

    # [MIGRATION]: Add is_priority_refined if it doesn't exist in older databases
    try:
        cursor.execute("SELECT is_priority_refined FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("Database Migration: Adding is_priority_refined column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN is_priority_refined BOOLEAN DEFAULT 0")
    
    # [PATCH]: Ensure index for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_user_email ON emails(user_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_gmail_id ON emails(gmail_id)")
    
    # Migration: Add columns if they don't exist in an older database
    try:
        cursor.execute("ALTER TABLE emails ADD COLUMN is_inbox BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass # already exists
    try:
        cursor.execute("ALTER TABLE emails ADD COLUMN is_sent BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass # already exists
    
    # Index for faster filtering on is_inbox/is_sent
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_category ON emails (user_email, is_inbox, is_sent, is_trashed)")
    # Index for fast conversation thread lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_thread ON emails (user_email, thread_id)")
 
    # [MIGRATION]: Add attachment_content if it doesn't exist
    try:
        cursor.execute("SELECT attachment_content FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB] Database Migration: Adding attachment_content column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN attachment_content TEXT")
    
    # [MIGRATION]: Add is_ocr_processed if it doesn't exist
    try:
        cursor.execute("SELECT is_ocr_processed FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("Database Migration: Adding is_ocr_processed column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN is_ocr_processed BOOLEAN DEFAULT 0")
    
    # [MIGRATION]: Add followup_count if it doesn't exist
    try:
        cursor.execute("SELECT followup_count FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("[DB] Database Migration: Adding followup_count column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN followup_count INTEGER DEFAULT 0")
    
    # [MIGRATION]: Add recipient_email if it doesn't exist
    try:
        cursor.execute("SELECT recipient_email FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("Database Migration: Adding recipient_email column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN recipient_email TEXT")

    # [MIGRATION]: Add institute_name if it doesn't exist
    try:
        cursor.execute("SELECT institute_name FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("Database Migration: Adding institute_name column...")
        cursor.execute("ALTER TABLE emails ADD COLUMN institute_name TEXT")

    # [NEW] Table: user_sync_history (Tracks the History ID bookmark for incremental sync)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sync_history (
            user_email TEXT PRIMARY KEY,
            last_history_id TEXT,
            last_sync_completed TIMESTAMP,
            consecutive_errors INTEGER DEFAULT 0
        )
    """)

    # [NEW] Table: sync_audit (Government-grade audit trail for every sync cycle)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            sync_type TEXT, -- 'INCREMENTAL' or 'FULL'
            status TEXT,    -- 'SUCCESS' or 'FAILED'
            duration_ms INTEGER,
            messages_added INTEGER DEFAULT 0,
            messages_deleted INTEGER DEFAULT 0,
            error_message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_audit_user ON sync_audit(user_email, timestamp)")
    
    conn.commit()
    conn.close()


def save_emails_batch(user_email: str, emails: List[Dict[str, Any]]):
    """Save or update a batch of emails in the database."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    def _save_params(email, user_email, is_trashed, new_is_inbox, new_is_sent, new_is_refined, new_is_ocr, attachments_json):
        return (
            email['email_id'],
            email.get('gmail_id'),
            email.get('thread_id'),
            email.get('parent_email_id'),
            email.get('sender'),
            email.get('sender_email'),
            email.get('recipient_email'),
            email.get('subject'),
            email.get('content'),
            email.get('category'),
            email.get('mail_type'),
            email.get('priority'),
            email.get('date'),
            email.get('has_attachment', False),
            attachments_json,
            email.get('is_demo', False),
            email.get('replied', False),
            is_trashed,
            new_is_inbox,
            new_is_sent,
            new_is_refined,
            new_is_ocr,
            email.get('attachment_content'),
            email.get('followup_count', 0),
            email.get('institute_name'),
            user_email
        )

    sql = """
        INSERT INTO emails (
            id, gmail_id, thread_id, parent_email_id, sender, sender_email, recipient_email, subject, content,
            category, mail_type, priority, date, has_attachment, attachments,
            is_demo, replied, is_trashed, is_inbox, is_sent, is_priority_refined, is_ocr_processed, attachment_content, followup_count, institute_name, user_email, last_synced
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
            followup_count=COALESCE(excluded.followup_count, followup_count),
            institute_name=COALESCE(excluded.institute_name, institute_name),
            last_synced=CURRENT_TIMESTAMP
    """

    for email in emails:
        # Check if already exists in our DB (Persistence check for trashed state)
        cursor.execute("SELECT is_trashed, is_inbox, is_sent, is_priority_refined, is_ocr_processed FROM emails WHERE id = ?", (email['email_id'],))
        existing = cursor.fetchone()
        
        is_trashed = 1 if email.get('category') == 'trash' or email.get('is_trashed') else (existing[0] if existing else 0)
        
        # Merge flags: If we found this email in INBOX fetch previously and now in SENT fetch, both bits should be 1
        new_is_inbox = 1 if email.get('is_inbox') else (existing[1] if existing else 0)
        new_is_sent = 1 if email.get('is_sent') else (existing[2] if existing else 0)
        new_is_refined = 1 if email.get('is_priority_refined') else (existing[3] if existing else 0)
        new_is_ocr = 1 if email.get('is_ocr_processed') else (existing[4] if existing else 0)
        
        attachments_raw = email.get('attachments', '[]')
        attachments_json = json.dumps(attachments_raw, ensure_ascii=False) if isinstance(attachments_raw, list) else attachments_raw
        
        cursor.execute(sql, _save_params(email, user_email, is_trashed, new_is_inbox, new_is_sent, new_is_refined, new_is_ocr, attachments_json))


    # --- THREAD STATE RECONCILIATION ---
    # For every thread touched in this batch, ensure 'replied' is set 
    # based on whether the LAST email in that thread is a genuine 'SENT' reply.
    # Exclude self-sent emails from marking a thread as 'replied'.
    tids = {e.get('thread_id') for e in emails if e.get('thread_id')}
    for tid in tids:
        # Find the latest message in this thread that is NOT a self-sent test
        cursor.execute("""
            SELECT is_sent, is_inbox FROM emails 
            WHERE thread_id = ? AND user_email = ? AND is_trashed = 0
            ORDER BY date DESC LIMIT 1
        """, (tid, user_email))
        latest = cursor.fetchone()
        
        if latest:
            # A thread is 'replied' ONLY if the latest message was sent by you 
            # AND it's not in your own inbox (i.e. it was sent to someone else).
            is_sent, is_in_inbox = latest
            is_replied_state = 1 if (is_sent and not is_in_inbox) else 0
            
            # Update all emails in this thread to match the new 'replied' state
            cursor.execute("""
                UPDATE emails SET replied = ? 
                WHERE thread_id = ? AND user_email = ?
            """, (is_replied_state, tid, user_email))
    
    conn.commit()
    conn.close()

def reconcile_email_flags(user_email: str, folder_type: str, active_gmail_ids: Set[str]):
    """
    Ensure parity between Gmail and Local DB for a specific folder.
    - Negative Sync: Unsets the flag locally if missing from Gmail.
    - Positive Sync: Sets the flag locally if present in Gmail (restores corrupted state).
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    flag_column = {
        'inbox': 'is_inbox',
        'sent': 'is_sent',
        'trash': 'is_trashed'
    }.get(folder_type)
    
    if not flag_column:
        conn.close()
        return

    # Base params for both operations
    base_where = "user_email = ? AND is_demo = 0 AND gmail_id IS NOT NULL"

    # --- 1. POSITIVE RECONCILIATION (Ensure what is in Gmail is in System) ---
    if active_gmail_ids:
        placeholders = ",".join(["?"] * len(active_gmail_ids))
        pos_query = f"UPDATE emails SET {flag_column} = 1"
        if folder_type == 'trash':
            pos_query += ", category = 'trash'"
        pos_query += f" WHERE {base_where} AND {flag_column} = 0 AND gmail_id IN ({placeholders})"
        
        cursor.execute(pos_query, [user_email] + list(active_gmail_ids))
        pos_changes = conn.total_changes
        if pos_changes > 0:
            print(f"✅ [Reconcile] Restored {pos_changes} emails to local {folder_type} (Matched Gmail).")

    # --- 2. NEGATIVE RECONCILIATION (Ensure what is NOT in Gmail is NOT in System) ---
    neg_query = f"UPDATE emails SET {flag_column} = 0"
    if folder_type == 'trash':
        neg_query += ", category = 'Miscellaneous'"
    neg_query += f" WHERE {base_where} AND {flag_column} = 1"
    
    if active_gmail_ids:
        neg_query += f" AND gmail_id NOT IN ({placeholders})"
        cursor.execute(neg_query, [user_email] + list(active_gmail_ids))
    else:
        cursor.execute(neg_query, [user_email])
        
    neg_changes = conn.total_changes - (pos_changes if active_gmail_ids else 0)
    if neg_changes > 0:
        print(f"🔄 [Reconcile] Removed {neg_changes} emails from local {folder_type} (Ghost check).")
        # Update last_synced for emails that were modified
        cursor.execute(f"UPDATE emails SET last_synced = CURRENT_TIMESTAMP WHERE {base_where} AND {flag_column} = 0", [user_email])
        
    conn.commit()
    conn.close()

def purge_orphaned_emails(user_email: str, retention_days: int = 30):
    """
    Permanently delete emails that are no longer in ANY Gmail folder (Inbox, Sent, Trash)
    and have been in this 'orphaned' state for longer than the retention period.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    # An 'orphaned' email has all major status flags set to 0 and is not a local demo email.
    # We use last_synced to track how long it has been since its flags were reconciled to 0.
    query = """
        DELETE FROM emails 
        WHERE user_email = ? 
          AND is_inbox = 0 
          AND is_sent = 0 
          AND is_trashed = 0 
          AND is_demo = 0
          AND last_synced < datetime('now', '-' || ? || ' days')
    """
    
    cursor.execute(query, (user_email, retention_days))
    purged_count = conn.total_changes
    
    if purged_count > 0:
        print(f"🚮 [Cleanup] Permanently purged {purged_count} records older than {retention_days} days to save storage.")
    
    conn.commit()
    conn.close()
    return purged_count

def mark_as_trashed(user_email: str, email_id: str, is_trashed: bool = True):
    """Mark an email as trashed in the local database for a specific user."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
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
    conn.close()

def get_emails_from_db(user_email: str, category: str = 'all', is_demo: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Retrieve emails from the database with filtering."""
    conn = sqlite3.connect(DB_PATH)
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
        # Broad fetch for Miscellaneous folder to exclude all main categories
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
        # Filtering by a specific grievance category (e.g. 'Semester / Examination')
        query += " AND category = ? AND is_inbox = 1 AND is_trashed = 0"
        params.append(db_category)
        
    if is_demo is not None:
        query += " AND is_demo = ?"
        params.append(1 if is_demo else 0)
        
    query += " ORDER BY priority ASC, date DESC"
    
    print(f"DEBUG SQL: {query} | Params: {params}")
    cursor.execute(query, params)
    rows = cursor.fetchall()
    print(f"DEBUG SQL RESULT: Found {len(rows)} rows for category '{category}'")
    conn.close()
    
    result = []
    for row in rows:
        email = dict(row)
        # Convert types to match frontend expectations
        email['email_id'] = email['id']
        email['hasAttachment'] = bool(email['has_attachment'])
        email['is_demo'] = bool(email['is_demo'])
        email['replied'] = bool(email['replied'])
        email['emailDate'] = email['date']
        email['attachments'] = json.loads(email['attachments'] or '[]')
        result.append(email)
        
    return result

def update_email_attachment_content(user_email: str, email_id: str, text: str, filename: str = None):
    """Specifically update or replace attachment OCR text for an email."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    # Check current content
    cursor.execute("SELECT attachment_content FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
    row = cursor.fetchone()
    current_content = row[0] if row and row[0] else ""
    
    new_content = current_content
    
    if filename:
        import re
        # Format: --- [Extracted from Attachment: filename] ---
        header_text = f"--- [Extracted from Attachment: {filename}] ---"
        # Pattern matches one instance of a block for this attachment
        pattern = rf"\n*?{re.escape(header_text)}.*?(?=\n--- \[Extracted from Attachment:|$)"
        
        # Aggressively remove EVERY existing block for this filename to fix legacy duplicates
        clean_content = re.sub(pattern, "", current_content, flags=re.DOTALL).strip()
        
        # Append the single fresh extraction
        new_content = (clean_content + "\n" + text.strip()).strip()
    else:
        # Simple deduplicated append
        if text.strip() and text.strip() not in current_content:
            new_content = (current_content + "\n" + text.strip()).strip()
            
    cursor.execute(
        "UPDATE emails SET attachment_content = ?, last_synced = CURRENT_TIMESTAMP WHERE id = ? AND user_email = ?",
        (new_content, email_id, user_email)
    )
    conn.commit()
    conn.close()

def get_existing_gmail_ids(user_email: str) -> set:
    """Return a set of all Gmail IDs already present in the database for this user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT gmail_id FROM emails WHERE user_email = ? AND gmail_id IS NOT NULL", (user_email,))
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return ids

def delete_all_for_user(user_email: str):
    """Clear user data (useful for full re-sync)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM emails WHERE user_email = ?", (user_email,))
    conn.commit()
    conn.close()

def revoke_user_session(user_email: str, reason: str = 'Google Security Event'):
    """Forcefully revoke a user's access due to a security event."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO revoked_sessions (user_email, reason) VALUES (?, ?)", (user_email.strip().lower(), reason))
    conn.commit()
    conn.close()

def is_user_revoked(user_email: str) -> bool:
    """Check if a user's session has been revoked."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM revoked_sessions WHERE user_email = ?", (user_email.strip().lower(),))
    revoked = cursor.fetchone() is not None
    conn.close()
    return revoked

def get_refinement_stats(user_email: str) -> Dict[str, int]:
    """Calculate the count of refined emails vs total emails for the user's refinement progress."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Total inbox emails (not trashed)
    cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0", (user_email,))
    total = cursor.fetchone()[0] or 0
    # Refined emails (not trashed)
    cursor.execute("SELECT COUNT(*) FROM emails WHERE user_email = ? AND is_priority_refined = 1 AND is_inbox = 1 AND is_trashed = 0", (user_email,))
    refined = cursor.fetchone()[0] or 0
    conn.close()
    return {"refined": refined, "total": total}

def save_chat_message(user_email: str, session_id: str, role: str, message: str):
    """Save a single chat message to history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (user_email, session_id, role, message) VALUES (?, ?, ?, ?)",
        (user_email, session_id, role, message)
    )
    conn.commit()
    conn.close()

def get_chat_history(user_email: str, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """Retrieve the RECENT chat history for a session (latest N messages, sorted chronologically)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # We use a subquery to get the latest messages first, then re-sort them chronologically
    cursor.execute(f"""
        SELECT role, message FROM (
            SELECT role, message, timestamp FROM chat_history 
            WHERE user_email = ? AND session_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ) ORDER BY timestamp ASC
    """, (user_email, session_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
def reclassify_all_stored_emails(classify_func):
    """
    Utility to re-run categorization for all emails in the database.
    Used for repairing/upgrading existing data after a classifier logic update.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Fetch all records
    cursor.execute("SELECT id, subject, content, attachment_content FROM emails")
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return 0
        
    print(f"📦 [Repair] Starting reclassification of {len(rows)} database records...")
    
    # 2. Re-classify and update
    updates = []
    for row in rows:
        new_category = classify_func(
            row['content'], 
            subject=row['subject'], 
            attachment_content=row['attachment_content']
        )
        updates.append((new_category, row['id']))
        
    # 3. Batch Update
    cursor.executemany("UPDATE emails SET category = ? WHERE id = ?", updates)
    
    conn.commit()
    conn.close()
    print(f"✅ [Repair] Successfully reclassified {len(updates)} emails.")
    return len(updates)

def get_pending_ocr_emails(user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch emails that have attachments but haven't been OCR processed yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM emails 
        WHERE user_email = ? 
          AND has_attachment = 1 
          AND is_ocr_processed = 0 
          AND is_trashed = 0
        LIMIT ?
    """, (user_email, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        d = dict(row)
        d['attachments'] = json.loads(d['attachments'] or '[]')
        result.append(d)
    return result

def touch_user_sync_time(user_email: str):
    """Update last_synced for all an user's inbox emails to current time to mark a successful sync check."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE emails 
        SET last_synced = CURRENT_TIMESTAMP 
        WHERE user_email = ? AND is_inbox = 1 AND is_trashed = 0
    """, (user_email,))
    conn.commit()
    conn.close()
    print(f"🕒 [Audit]: Touched sync timestamp for {user_email}")

def get_user_sync_history(user_email: str) -> Optional[Dict[str, Any]]:
    """Retrieve the last sync history for a user."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_sync_history WHERE user_email = ?", (user_email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_sync_history(user_email: str, history_id: str, reset_errors: bool = True):
    """Update or create the sync history for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if reset_errors:
        cursor.execute("""
            INSERT INTO user_sync_history (user_email, last_history_id, last_sync_completed, consecutive_errors)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(user_email) DO UPDATE SET
                last_history_id = excluded.last_history_id,
                last_sync_completed = excluded.last_sync_completed,
                consecutive_errors = 0
        """, (user_email, history_id, now))
    else:
        cursor.execute("""
            INSERT INTO user_sync_history (user_email, last_history_id, last_sync_completed)
            VALUES (?, ?, ?)
            ON CONFLICT(user_email) DO UPDATE SET
                last_history_id = excluded.last_history_id,
                last_sync_completed = excluded.last_sync_completed
        """, (user_email, history_id, now))
    conn.commit()
    conn.close()

def log_sync_audit(user_email: str, sync_type: str, status: str, duration_ms: int, added: int = 0, deleted: int = 0, error: str = None):
    """Log a sync cycle result for administrative audit."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sync_audit (user_email, sync_type, status, duration_ms, messages_added, messages_deleted, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_email, sync_type, status, duration_ms, added, deleted, error))
    conn.commit()
    conn.close()

def increment_sync_error(user_email: str):
    """Increment consecutive error count for backoff logic."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE user_sync_history SET consecutive_errors = consecutive_errors + 1 WHERE user_email = ?", (user_email,))
    conn.commit()
    conn.close()

def get_consecutive_sync_errors(user_email: str) -> int:
    """Get count of errors for backoff."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT consecutive_errors FROM user_sync_history WHERE user_email = ?", (user_email,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

