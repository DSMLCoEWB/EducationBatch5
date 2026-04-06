import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grievances.db")

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create the emails table with is_inbox and is_sent flags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            gmail_id TEXT UNIQUE,
            thread_id TEXT,
            sender TEXT,
            sender_email TEXT,
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
            user_email TEXT,
            last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create the revoked_sessions table for Google RISC security notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revoked_sessions (
            user_email TEXT PRIMARY KEY,
            revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
    """)
    
    # [MIGRATION]: Add is_priority_refined if it doesn't exist in older databases
    try:
        cursor.execute("SELECT is_priority_refined FROM emails LIMIT 1")
    except sqlite3.OperationalError:
        print("💾 Database Migration: Adding is_priority_refined column...")
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
    
    conn.commit()
    conn.close()

def save_emails_batch(user_email: str, emails: List[Dict[str, Any]]):
    """Save or update a batch of emails in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for email in emails:
        # Check if already exists in our DB (Persistence check for trashed state)
        cursor.execute("SELECT is_trashed, is_inbox, is_sent, is_priority_refined FROM emails WHERE id = ?", (email['email_id'],))
        existing = cursor.fetchone()
        
        is_trashed = 1 if email.get('category') == 'trash' or email.get('is_trashed') else (existing[0] if existing else 0)
        
        # Merge flags: If we found this email in INBOX fetch previously and now in SENT fetch, both bits should be 1
        new_is_inbox = 1 if email.get('is_inbox') else (existing[1] if existing else 0)
        new_is_sent = 1 if email.get('is_sent') else (existing[2] if existing else 0)
        new_is_refined = 1 if email.get('is_priority_refined') else (existing[3] if existing else 0) # <--- ADDED
        
        attachments_raw = email.get('attachments', '[]')
        attachments_json = json.dumps(attachments_raw, ensure_ascii=False) if isinstance(attachments_raw, list) else attachments_raw
        
        cursor.execute("""
            INSERT INTO emails (
                id, gmail_id, thread_id, sender, sender_email, subject, content,
                category, mail_type, priority, date, has_attachment, attachments,
                is_demo, replied, is_trashed, is_inbox, is_sent, is_priority_refined, user_email, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                gmail_id=excluded.gmail_id,
                thread_id=excluded.thread_id,
                sender=excluded.sender,
                sender_email=excluded.sender_email,
                subject=excluded.subject,
                content=excluded.content,
                category=CASE 
                    WHEN is_trashed=1 OR excluded.is_trashed=1 THEN 'trash' 
                    WHEN category IS NULL OR category = 'Sent' OR category = '' THEN excluded.category 
                    ELSE category 
                END,
                mail_type=excluded.mail_type,
                priority=excluded.priority,
                date=excluded.date,
                has_attachment=excluded.has_attachment,
                attachments=excluded.attachments,
                replied=MIN(replied, excluded.replied),
                is_trashed=MAX(is_trashed, excluded.is_trashed),
                is_inbox=MAX(is_inbox, excluded.is_inbox),
                is_sent=MAX(is_sent, excluded.is_sent),
                is_priority_refined=MAX(is_priority_refined, excluded.is_priority_refined),
                last_synced=CURRENT_TIMESTAMP
        """, (
            email['email_id'],
            email.get('gmail_id'),
            email.get('thread_id'),
            email.get('sender'),
            email.get('sender_email'),
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
            user_email
        ))
    
    conn.commit()
    conn.close()

def mark_as_trashed(user_email: str, email_id: str, is_trashed: bool = True):
    """Mark an email as trashed in the local database for a specific user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE emails SET is_trashed = ?, category = ? WHERE id = ? AND user_email = ?", 
        (1 if is_trashed else 0, 'trash' if is_trashed else 'miscellaneous', email_id, user_email)
    )
    conn.commit()
    conn.close()

def get_emails_from_db(user_email: str, category: str = 'all', is_demo: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Retrieve emails from the database with filtering."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Map frontend IDs to actual DB category strings from classifier.py
    category_map = {
        'suspension': 'Suspension / Disciplinary',
        'fir': 'FIR / Arrest / Legal',
        'semester': 'Semester / Examination',
        'miscellaneous': 'Miscellaneous'
    }
    db_category = category_map.get(category, category)
    
    query = "SELECT * FROM emails WHERE user_email = ?"
    params = [user_email]
    
    if category == 'trash':
        query += " AND is_trashed = 1"
    elif category == 'all' or category == 'dashboard':
        query += " AND is_inbox = 1 AND is_trashed = 0"
    elif category == 'Sent':
        query += " AND is_sent = 1 AND is_trashed = 0"
    elif category == 'miscellaneous':
        # Broad fetch for Miscellaneous folder to include 'Service' matters and others
        query += " AND category NOT IN (?, ?, ?) AND is_inbox = 1 AND is_trashed = 0"
        params.extend(['Suspension / Disciplinary', 'FIR / Arrest / Legal', 'Semester / Examination'])
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

def get_existing_gmail_ids(user_email: str) -> set[str]:
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
