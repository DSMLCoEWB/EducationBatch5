"""
One-time migration script: Fixes is_inbox=0 and is_sent=0 for all existing emails.

After the schema change, ALL existing emails were written with both flags=0,
which hides them from every view. This script:
  - Sets is_inbox=1 for all non-trashed emails NOT in 'Sent' category
  - Sets is_sent=1 for all emails in 'Sent' category
  - Also resets the stale 'replied' flag for self-sent inbox emails

Run once with: python migrate_flags.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grievances.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found at:", DB_PATH)
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Step 0: Check the current state
    cursor.execute("SELECT COUNT(*) FROM emails")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM emails WHERE is_inbox=1")
    inbox_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM emails WHERE is_sent=1")
    sent_count = cursor.fetchone()[0]

    print(f"📊 Before migration: {total} total, {inbox_count} inbox, {sent_count} sent")

    # Step 1: Set is_inbox=1 for all non-trashed emails that are NOT in 'Sent' category
    # (These are the grievances sitting in the Inbox)
    cursor.execute("""
        UPDATE emails
        SET is_inbox = 1
        WHERE is_trashed = 0 AND (category != 'Sent' OR category IS NULL)
    """)
    print(f"  ✅ Set is_inbox=1 for {cursor.rowcount} rows")

    # Step 2: Set is_sent=1 for all emails that were explicitly fetched from Sent
    # Since we stored category='Sent' for those, use that as a proxy
    cursor.execute("""
        UPDATE emails
        SET is_sent = 1
        WHERE category = 'Sent' AND is_trashed = 0
    """)
    print(f"  ✅ Set is_sent=1 for {cursor.rowcount} rows")

    # Step 3: Fix the 'replied' flag - reset for self-sent inbox emails
    # If sender_email == user_email AND is_inbox=1, it's a self-test, not a real reply
    cursor.execute("""
        UPDATE emails
        SET replied = 0
        WHERE is_inbox = 1 AND sender_email = user_email
    """)
    print(f"  ✅ Reset replied flag for {cursor.rowcount} self-sent inbox emails")

    conn.commit()

    # Step 4: Verify
    cursor.execute("SELECT COUNT(*) FROM emails WHERE is_inbox=1")
    new_inbox = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM emails WHERE is_sent=1")
    new_sent = cursor.fetchone()[0]

    conn.close()
    print(f"\n📊 After migration: {total} total, {new_inbox} inbox, {new_sent} sent")
    print(f"\n🎉 Migration complete! Restart your backend server and click Refresh.")

if __name__ == "__main__":
    migrate()
