import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "grievances.db")

def backfill_institutes():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Improved heuristic: Get the domain part, but ignore common public providers
    PUBLIC_PROVIDERS = "('gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com', 'rediffmail.com', 'live.com', 'me.com')"
    
    cursor.execute(f"""
        UPDATE emails 
        SET institute_name = CASE 
            WHEN substr(sender_email, instr(sender_email, '@') + 1) IN {PUBLIC_PROVIDERS} THEN 'Individual / Public'
            ELSE UPPER(substr(sender_email, instr(sender_email, '@') + 1, instr(substr(sender_email, instr(sender_email, '@') + 1), '.') - 1))
        END
        WHERE sender_email IS NOT NULL 
          AND instr(sender_email, '@') > 0
          AND instr(substr(sender_email, instr(sender_email, '@') + 1), '.') > 0
    """)
    
    changes = conn.total_changes
    conn.commit()
    conn.close()
    
    print(f"[DB] Successfully backfilled {changes} records with institute names from email domains.")

if __name__ == "__main__":
    backfill_institutes()
