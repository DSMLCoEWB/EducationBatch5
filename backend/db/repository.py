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
        
    result = []
    for row in rows:
        email = dict(row)
        # Type Conversion for Frontend Parity
        email['email_id']      = email['id']
        email['parentEmailId'] = email.get('parent_email_id')
        email['threadId']      = email.get('thread_id')
        email['mailType']      = email.get('mail_type')
        email['followUpCount'] = email.get('followup_count', 0)
        email['emailDate']     = email.get('date')
        email['senderEmail']   = email.get('sender_email')
        email['instituteName'] = email.get('institute_name')
        
        email['hasAttachment'] = bool(email.get('has_attachment'))
        email['is_demo']       = bool(email.get('is_demo'))
        email['replied']       = bool(email.get('replied'))
        email['attachments']   = json.loads(email.get('attachments') or '[]')
        result.append(email)
        
    return result


def save_emails_batch(user_email: str, emails: List[Dict[str, Any]]):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
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
            cursor.execute("SELECT is_trashed, is_inbox, is_sent, is_priority_refined, is_ocr_processed FROM emails WHERE id = ?", (email['email_id'],))
            existing = cursor.fetchone()
            
            is_trashed = 1 if email.get('category') == 'trash' or email.get('is_trashed') else (existing[0] if existing else 0)
            new_is_inbox = 1 if email.get('is_inbox') else (existing[1] if existing else 0)
            new_is_sent = 1 if email.get('is_sent') else (existing[2] if existing else 0)
            new_is_refined = 1 if email.get('is_priority_refined') else (existing[3] if existing else 0)
            new_is_ocr = 1 if email.get('is_ocr_processed') else (existing[4] if existing else 0)
            
            attachments_raw = email.get('attachments', '[]')
            attachments_json = json.dumps(attachments_raw, ensure_ascii=False) if isinstance(attachments_raw, list) else attachments_raw
            # Category Normalization Map (from repair_categories.py)
            NORM_MAP = {
                "Examination / Semester": "Semester / Examination",
                "Misc": "Miscellaneous",
                "miscellaneous": "Miscellaneous",
                "Others": "Miscellaneous",
                "other": "Miscellaneous"
            }
            
            # Apply Normalization
            cat = email.get("category", "Miscellaneous")
            cat = NORM_MAP.get(cat, cat)

            params = (
                email['email_id'],
                email.get('gmail_id'),
                email.get('thread_id'),
                email.get('parent_email_id'),
                email.get('sender'),
                email.get('sender_email'),
                email.get('recipient_email'),
                email.get('subject'),
                email.get('content'),
                cat,
                email.get('mail_type'),
                email.get('priority', 6),
                email.get('date'),
                1 if email.get('has_attachment') else 0,
                attachments_json,
                1 if email.get('is_demo') else 0,
                1 if email.get('replied') else 0,
                is_trashed,
                new_is_inbox,
                new_is_sent,
                new_is_refined,
                new_is_ocr,
                email.get('attachment_content', ''),
                email.get('followup_count', 0),
                email.get('institute_name'),
                user_email
            )
            
            cursor.execute(sql, params)

        # Thread Reconciliation
        _reconcile_thread_replied_state(cursor, user_email, emails)
        conn.commit()

        # Thread Reconciliation
        _reconcile_thread_replied_state(cursor, user_email, emails)
        conn.commit()

def _reconcile_thread_replied_state(cursor, user_email, emails):
    tids = {e.get('thread_id') for e in emails if e.get('thread_id')}
    for tid in tids:
        cursor.execute("""
            SELECT is_sent, is_inbox FROM emails 
            WHERE thread_id = ? AND user_email = ? AND is_trashed = 0
            ORDER BY date DESC LIMIT 1
        """, (tid, user_email))
        latest = cursor.fetchone()
        if latest:
            is_sent, is_in_inbox = latest
            is_replied_state = 1 if (is_sent and not is_in_inbox) else 0
            cursor.execute("UPDATE emails SET replied = ? WHERE thread_id = ? AND user_email = ?", (is_replied_state, tid, user_email))

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

def update_email_attachment_content(user_email: str, email_id: str, text: str, filename: str = None):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT attachment_content FROM emails WHERE id = ? AND user_email = ?", (email_id, user_email))
        row = cursor.fetchone()
        current_content = row[0] if row and row[0] else ""
        new_content = current_content
        if filename:
            import re
            header_text = f"--- [Extracted from Attachment: {filename}] ---"
            pattern = rf"\n*?{re.escape(header_text)}.*?(?=\n--- \[Extracted from Attachment:|$)"
            clean_content = re.sub(pattern, "", current_content, flags=re.DOTALL).strip()
            new_content = (clean_content + "\n" + text.strip()).strip()
        else:
            if text.strip() and text.strip() not in current_content:
                new_content = (current_content + "\n" + text.strip()).strip()
        
        # Mark as OCR processed
        cursor.execute("""
            UPDATE emails 
            SET attachment_content = ?, is_ocr_processed = 1, last_synced = CURRENT_TIMESTAMP 
            WHERE id = ? AND user_email = ?
        """, (new_content, email_id, user_email))
        conn.commit()

def get_unrefined_emails(user_email: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Returns a batch of emails that need AI priority/category refinement."""
    with get_db_conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender, subject, content 
            FROM emails 
            WHERE user_email = ? AND is_priority_refined = 0 AND is_trashed = 0 
            ORDER BY date DESC LIMIT ?
        """, (user_email, limit))
        return [dict(row) for row in cursor.fetchall()]

def update_email_refinement(user_email: str, email_id: str, priority: int, category: str):
    """Updates an email with AI-refined priority and category labels."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE emails 
            SET priority = ?, category = ?, is_priority_refined = 1, last_synced = CURRENT_TIMESTAMP 
            WHERE id = ? AND user_email = ?
        """, (priority, category, email_id, user_email))
        conn.commit()

def get_unprocessed_attachments(user_email: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Returns attachments that exist locally but haven't been OCR-processed yet."""
    import json
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
            atts = json.loads(row['attachments'] or '[]')
            for att in atts:
                filename = att.get('filename')
                if filename:
                    from config import ATTACHMENTS_DIR
                    path = os.path.join(ATTACHMENTS_DIR, filename)
                    if os.path.exists(path):
                        results.append({
                            "email_id": row['email_id'],
                            "filename": filename,
                            "local_path": path
                        })
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
