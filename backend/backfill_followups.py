import sqlite3
import pandas as pd
import os
import sys

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database_api import DB_PATH, save_emails_batch
from followup import detect_followup

def backfill_followups():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    # Extract all emails to process in memory
    df_all = pd.read_sql_query("SELECT * FROM emails ORDER BY date ASC", conn)
    conn.close()

    if df_all.empty:
        print("No emails found to backfill.")
        return

    print(f"Starting backfill for {len(df_all)} emails...")
    
    # Process per user (since followup context is per-user)
    updated_records = []
    for user_email in df_all['user_email'].unique():
        user_df = df_all[df_all['user_email'] == user_email].copy()
        
        # We'll build up a context DF like main.py does
        context_df = pd.DataFrame()
        
        for _, row in user_df.iterrows():
            # Detect followup status
            mail_type, parent_id, followup_count = detect_followup(row.to_dict(), context_df)
            
            # Prepare update record
            # We must map 'id' back to 'email_id' for save_emails_batch
            update_rec = row.to_dict()
            update_rec['email_id'] = row['id']
            update_rec['mail_type'] = mail_type
            update_rec['followup_count'] = followup_count
            update_rec['parent_email_id'] = parent_id
            
            updated_records.append(update_rec)
            
            # Update context for next email in the loop
            context_df = pd.concat([context_df, pd.DataFrame([update_rec])], ignore_index=True)

    if updated_records:
        # Use existing batch save logic to preserve trashed/sent states correctly
        # We'll do this in chunks to avoid locking issues if the user is syncing
        chunk_size = 50
        for i in range(0, len(updated_records), chunk_size):
            chunk = updated_records[i : i + chunk_size]
            # Group by user_email for the batch save function requirements
            user_groups = {}
            for rec in chunk:
                u = rec['user_email']
                if u not in user_groups: user_groups[u] = []
                user_groups[u].append(rec)
            
            for u, recs in user_groups.items():
                save_emails_batch(u, recs)
        
        print(f"Successfully backfilled follow-up counts for {len(updated_records)} records.")

if __name__ == "__main__":
    backfill_followups()
