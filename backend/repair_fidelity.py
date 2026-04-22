import sqlite3
import json
import os
import re
from pathlib import Path

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "grievances.db"
ATTACHMENTS_DIR = BASE_DIR / "attachments"

def repair_database_fidelity_v3():
    """
    Surgical repair of database records:
    1. Removes redundant 'hard-fallback' HTML to fix paragraph spacing.
    2. Re-maps CIDs for inline images.
    3. Normalizes 'attachments' structure to ensure UI can render cards.
    """
    print("[Fidelity Repair V3] Starting restoration...")
    
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch all emails
    cursor.execute("SELECT id, content, html_content, attachments FROM emails")
    emails = cursor.fetchall()
    
    print(f"Analyzing {len(emails)} emails...")
    
    repaired_count = 0
    cid_remapped_count = 0
    structure_fixed_count = 0
    
    for row in emails:
        email_id = row['id']
        content = row['content'] or ""
        html_content = row['html_content'] or ""
        attachments_raw = row['attachments'] or "[]"
        
        needs_update = False
        new_html = html_content
        new_attachments_json = attachments_raw
        
        # --- A. PARAGRAPH FIX ---
        is_actually_html = any(tag in str(html_content).lower() for tag in ['<div', '<p', '<br', '<html', '<table'])
        if not is_actually_html and html_content:
            new_html = None
            needs_update = True

        # --- B. ATTACHMENT STRUCTURE FIX ---
        try:
            current_atts = json.loads(attachments_raw)
            # If it's a list of strings, convert to list of objects
            if current_atts and isinstance(current_atts, list) and isinstance(current_atts[0], str):
                new_atts = []
                for fname in current_atts:
                    new_atts.append({"filename": fname, "local_path": os.path.join(str(ATTACHMENTS_DIR), fname)})
                new_attachments_json = json.dumps(new_atts)
                needs_update = True
                structure_fixed_count += 1
        except Exception:
            pass

        # --- C. CID RE-MAPPING ---
        if is_actually_html and html_content and "cid:" in html_content:
            try:
                attachments = json.loads(new_attachments_json)
                cid_map = {}
                for att in attachments:
                    if isinstance(att, dict):
                        cid = att.get("content_id")
                        local_path = att.get("local_path")
                        if cid and local_path:
                            unique_fname = os.path.basename(local_path)
                            cid_map[cid] = unique_fname
                
                if cid_map:
                    original_html = new_html if new_html else html_content
                    for cid, unique_fname in cid_map.items():
                        pattern = rf'src=["\']cid:{re.escape(cid)}["\']'
                        replacement = f'src="__API_BASE_URL__/emails/download/attachment/{unique_fname}"'
                        new_html = re.sub(pattern, replacement, original_html)
                    
                    if new_html != original_html:
                        cid_remapped_count += 1
                        needs_update = True
            except Exception:
                pass

        if needs_update:
            cursor.execute(
                "UPDATE emails SET html_content = ?, attachments = ? WHERE id = ?",
                (new_html, new_attachments_json, email_id)
            )
            repaired_count += 1

    conn.commit()
    conn.close()
    
    print("\n[Fidelity Repair V3] Complete!")
    print(f"Paragraphs restored: {repaired_count}")
    print(f"Attachment logic fixed: {structure_fixed_count}")
    print(f"Images re-mapped: {cid_remapped_count}")
    print("Please RESTART backend and REFRESH browser.")

if __name__ == "__main__":
    repair_database_fidelity_v3()
