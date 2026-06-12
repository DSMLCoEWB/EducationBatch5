"""
Import Government Email PDFs into Grievance Database
=====================================================
Usage:
    1. Place all 52 PDF attachments into backend/import_emails/
    2. Run:  python backend/scripts/import_gov_emails.py
    
Each PDF is a printed/scanned email from real government grievances.
The script extracts text, uses Gemini to parse email fields, and inserts
them into the DB via save_emails_batch().
"""

import os
import sys
import json
import hashlib
import re
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- Setup paths ---
# Add parent directory of scripts (which is backend/) to sys.path so we can import config, db, services
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "src"))

IMPORT_DIR = BASE_DIR / "storage" / "import_emails"
USER_EMAIL = "coedsml.education@gmail.com"

# --- Imports from project ---
from db.repository import save_emails_batch, init_db
from data.demo_mapping import DEMO_TRIAGE_MAPPING

# Initialize DB
init_db()


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF using pdfplumber, with Gemini Vision OCR fallback."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"  ⚠️ pdfplumber failed for {pdf_path.name}: {e}")
    
    # OCR fallback if text is too short
    if len(text.strip()) < 50:
        print(f"  🔍 OCR fallback for {pdf_path.name}...")
        try:
            from services.ocr_service import extract_text_from_attachment_ai
            ocr_text = extract_text_from_attachment_ai(str(pdf_path))
            if ocr_text:
                text = ocr_text
        except Exception as e:
            print(f"  ❌ OCR fallback failed: {e}")
    
    return text.strip()


def parse_email_fields_regex(raw_text: str, filename: str) -> dict:
    """Parse email fields from Gmail print-to-PDF format.
    
    Typical format:
      Line 0: "5/13/26, 3:14 PM Gmail - <subject>"
      Line 1: "DTE Office Directorate of Technical Education <techedndirectoratewb@gmail.com>"
      Line 2: "<subject>"
      Line 3: "<Sender Name> <sender@email.com> <date>"
      Line 4: "To: <recipients>"
      Line 5+: body
    """
    lines = raw_text.split("\n")
    
    sender_name = ""
    sender_email = ""
    recipient_email = ""
    to_full = ""  # Full "To:" line with all recipients
    cc_full = ""  # Full "Cc:" line
    subject = ""
    date_str = None
    body_start_idx = 0
    
    email_pattern = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
    
    # --- Strategy 1: Gmail print-to-PDF format ---
    # Line 0 often starts with a date like "5/13/26, 3:14 PM Gmail - subject"
    gmail_header = re.match(r'^\d+/\d+/\d+.*Gmail\s*-\s*(.+)', lines[0].strip()) if lines else None
    
    if gmail_header:
        subject = gmail_header.group(1).strip()
        
        # Scan lines for sender (line with email + date pattern) and To:
        for i, line in enumerate(lines[1:30], start=1):
            line = line.strip()
            
            # Look for "To:" line
            to_match = re.match(r'^To:\s*(.+)', line, re.IGNORECASE)
            if to_match and not to_full:
                to_val = to_match.group(1).strip()
                # To: can span multiple lines — collect continuation lines
                j = i + 1
                while j < min(len(lines), i + 5):
                    next_line = lines[j].strip()
                    if re.match(r'^(Cc|Bcc|Subject|From|Date|Sir|Madam|Dear|Respected)[:, ]', next_line, re.IGNORECASE) or not next_line:
                        break
                    # Looks like continuation (has emails or names)
                    if email_pattern.search(next_line):
                        to_val += " " + next_line
                        j += 1
                    else:
                        break
                to_full = to_val
                to_emails = email_pattern.findall(to_val)
                if to_emails:
                    recipient_email = to_emails[0]
                body_start_idx = max(body_start_idx, j)
                continue
            
            # Look for "Cc:" line
            cc_match = re.match(r'^Cc:\s*(.+)', line, re.IGNORECASE)
            if cc_match and not cc_full:
                cc_val = cc_match.group(1).strip()
                # Cc: can also span multiple lines
                j = i + 1
                while j < min(len(lines), i + 5):
                    next_line = lines[j].strip()
                    if re.match(r'^(To|Bcc|Subject|From|Date|Sir|Madam|Dear|Respected)[:, ]', next_line, re.IGNORECASE) or not next_line:
                        break
                    if email_pattern.search(next_line):
                        cc_val += " " + next_line
                        j += 1
                    else:
                        break
                cc_full = cc_val
                body_start_idx = max(body_start_idx, j)
                continue
            
            # Look for sender line: "Name <email> date"
            # Pattern: has an email AND has a date-like string (month name or digits with slashes)
            line_emails = email_pattern.findall(line)
            date_in_line = re.search(
                r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4})',
                line, re.IGNORECASE
            )
            
            if line_emails and date_in_line and not sender_email:
                sender_email = line_emails[0]
                # Extract name: everything before the email
                name_part = line[:line.find(sender_email)].strip().rstrip('<').strip()
                if name_part:
                    sender_name = name_part
                # Extract date
                date_str = date_in_line.group(1)
                body_start_idx = max(body_start_idx, i + 1)
                continue
            
            # Skip the mailbox owner line and repeated subject line
            if i <= 3:
                continue
            
            # If we've found sender and recipient, rest is body
            if sender_email and recipient_email:
                body_start_idx = max(body_start_idx, i)
                break
    else:
        # --- Strategy 2: Standard email header format (fallback) ---
        from_pattern = re.compile(r'(?:From|Sender)\s*[:：]\s*(.+)', re.IGNORECASE)
        to_pattern_std = re.compile(r'(?:To|Recipient)\s*[:：]\s*(.+)', re.IGNORECASE)
        subject_pattern = re.compile(r'(?:Subject|Sub|Subj|विषय)\s*[:：]\s*(.+)', re.IGNORECASE)
        date_pattern_std = re.compile(r'(?:Date|Dated|Dt|दिनांक)\s*[:：]\s*(.+)', re.IGNORECASE)
        
        header_zone = min(len(lines), 30)
        for i in range(header_zone):
            line = lines[i].strip()
            if not line:
                continue
            
            m = from_pattern.match(line)
            if m and not sender_name:
                from_val = m.group(1).strip()
                emails_in_line = email_pattern.findall(from_val)
                if emails_in_line:
                    sender_email = emails_in_line[0]
                    sender_name = email_pattern.sub('', from_val).strip().strip('<>').strip(',').strip()
                else:
                    sender_name = from_val
                body_start_idx = max(body_start_idx, i + 1)
                continue
            
            m = to_pattern_std.match(line)
            if m and not recipient_email:
                emails_in_line = email_pattern.findall(m.group(1))
                if emails_in_line:
                    recipient_email = emails_in_line[0]
                body_start_idx = max(body_start_idx, i + 1)
                continue
            
            m = subject_pattern.match(line)
            if m and not subject:
                subject = m.group(1).strip()
                body_start_idx = max(body_start_idx, i + 1)
                continue
            
            m = date_pattern_std.match(line)
            if m and not date_str:
                date_str = m.group(1).strip()
                body_start_idx = max(body_start_idx, i + 1)
                continue

    # --- Also check for forwarded message headers ---
    for i, line in enumerate(lines[:30]):
        fwd_from = re.match(r'^From:\s*(.+)', line.strip(), re.IGNORECASE)
        if fwd_from and not sender_email:
            fwd_emails = email_pattern.findall(fwd_from.group(1))
            if fwd_emails:
                sender_email = fwd_emails[0]
                name_part = email_pattern.sub('', fwd_from.group(1)).strip().strip('<>').strip(',').strip()
                if name_part and not sender_name:
                    sender_name = name_part
        
        fwd_subj = re.match(r'^Subject:\s*(.+)', line.strip(), re.IGNORECASE)
        if fwd_subj and not subject:
            # Multi-line subjects: join with next line if it doesn't look like a header
            subj_text = fwd_subj.group(1).strip()
            if i + 1 < len(lines) and not re.match(r'^(To|From|Date|Subject|Cc):', lines[i+1].strip(), re.IGNORECASE):
                subj_text += " " + lines[i+1].strip()
            subject = subj_text.strip()
        
        fwd_date = re.match(r'^Date:\s*(.+)', line.strip(), re.IGNORECASE)
        if fwd_date and not date_str:
            date_str = fwd_date.group(1).strip()
    
    # Fallback: scan text for any email address
    if not sender_email:
        all_emails = email_pattern.findall(raw_text[:1500])
        # Skip the mailbox owner email
        for e in all_emails:
            if e != "techedndirectoratewb@gmail.com":
                sender_email = e
                break
    
    # Parse date into YYYY-MM-DD
    parsed_date = None
    if date_str:
        date_formats = [
            "%d %B %Y", "%d %b %Y", "%d %B, %Y",
            "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
            "%d/%m/%y", "%d-%m-%y",
            "%B %d, %Y", "%b %d, %Y",
            "%Y-%m-%d",
        ]
        clean_date = re.sub(
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[,\s]*',
            '', date_str, flags=re.IGNORECASE
        ).strip()
        # Also strip "at HH:MM" time suffixes
        clean_date = re.sub(r'\s+at\s+\d+:\d+.*', '', clean_date).strip()
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(clean_date[:30].strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
    
    # Build body from remaining lines, skip Gmail footer/URL noise
    # Also reconstruct paragraphs to fix haphazard PDF newlines
    body_lines = []
    for line in lines[body_start_idx:]:
        clean = line.strip()
        if 'mail.google.com/mail' in clean:
            continue
        if re.match(r'^\d+/\d+/\d+.*Gmail\s*-', clean):
            continue
        body_lines.append(line) # Keep original line for now to check spacing
    
    # Smart Paragraph Reconstruction
    reconstructed_body = ""
    for i, line in enumerate(body_lines):
        stripped = line.strip()
        if not stripped:
            if not reconstructed_body.endswith("\n\n"):
                reconstructed_body += "\n\n"
            continue
        
        if not reconstructed_body or reconstructed_body.endswith("\n\n"):
            reconstructed_body += stripped
        else:
            # Smart Paragraph Reconstruction:
            # We only join lines that are clearly continuations.
            prev_line = body_lines[i-1].strip() if i > 0 else ""
            should_join = False
            if prev_line:
                # 1. ALWAYS join if the current line starts with a lowercase letter
                if stripped and stripped[0].islower():
                    should_join = True
                # 2. Join if the previous line doesn't end in any punctuation 
                # (Likely a mid-sentence layout wrap)
                elif not prev_line[-1] in ".!?:,;":
                    should_join = True
                # 3. Handle special cases like "Assistant [wrap] Professor"
                elif prev_line.split()[-1] in ["Assistant", "Associate", "Professor", "The", "and", "or"]:
                    should_join = True
            
            if should_join:
                reconstructed_body += " " + stripped
            else:
                # Keep the newline
                reconstructed_body += "\n" + stripped

    body = reconstructed_body.strip()
    if not body:
        body = raw_text
    
    return {
        "sender_name": sender_name or "Unknown Sender",
        "sender_email": sender_email or "unknown@gov.in",
        "recipient_email": recipient_email or "techedndirectoratewb@gmail.com",
        "to_full": to_full or recipient_email or "techedndirectoratewb@gmail.com",
        "cc_full": cc_full,
        "subject": subject or filename.replace(".pdf", "").replace("_", " ").replace("-", " "),
        "date": parsed_date,
        "body": body,
    }


def generate_stable_id(filename: str, content: str) -> str:
    """Generate a stable, reproducible ID from filename + content hash."""
    hash_input = f"gov_import_{filename}_{content[:200]}"
    return "gov_" + hashlib.sha256(hash_input.encode()).hexdigest()[:16]




def import_all_pdfs():
    """Main import function."""
    if not IMPORT_DIR.exists():
        print(f"[ERROR] Import directory not found: {IMPORT_DIR}")
        print(f"   Please create it and place the 52 PDF files inside.")
        sys.exit(1)
    
    pdf_files = list(IMPORT_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"[DIR] No PDF files found in {IMPORT_DIR}")
        return
        
    print(f"[DIR] Found {len(pdf_files)} PDF files in {IMPORT_DIR}")
    print(f"[USER] Importing for user: {USER_EMAIL}")
    print(f"{'='*60}")
    
    emails_to_insert = []
    failed = []
    
    for idx, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {pdf_path.name}")
        
        # Step 1: Extract text
        raw_text = extract_text_from_pdf(pdf_path)
        if not raw_text or len(raw_text) < 20:
            print(f"  [X] No text extracted, skipping.")
            failed.append(pdf_path.name)
            continue
        print(f"  [OK] Extracted {len(raw_text)} chars")
        
        # Step 2: Parse email fields with regex
        parsed = parse_email_fields_regex(raw_text, pdf_path.name)
        if not parsed:
            print(f"  [!] Regex parsing returned nothing, using raw text.")
            parsed = {
                "sender_name": "Unknown Sender",
                "sender_email": "unknown@gov.in",
                "recipient_email": "techedndirectoratewb@gmail.com",
                "subject": pdf_path.stem.replace("_", " ").replace("-", " "),
                "date": None,
                "body": raw_text
            }
        
        print(f"  [FROM] {parsed.get('sender_name', 'N/A')} <{parsed.get('sender_email', 'N/A')}>")
        print(f"  [SUBJ] {parsed.get('subject', 'N/A')}")
        print(f"  [DATE] {parsed.get('date', 'N/A')}")
        
        # Step 3: Build email record
        stable_id = generate_stable_id(pdf_path.name, raw_text)
        
        body = parsed.get("body") or raw_text
        subject = parsed.get("subject") or pdf_path.stem
        sender_name = parsed.get("sender_name") or "Unknown"
        sender_email = parsed.get("sender_email") or "unknown@gov.in"
        email_date = parsed.get("date")
        
        # Validate date format
        if email_date:
            try:
                datetime.strptime(email_date, "%Y-%m-%d")
                email_date = email_date + "T00:00:00Z"
            except ValueError:
                email_date = None
        
        if not email_date:
            email_date = datetime.now().strftime("%Y-%m-%dT00:00:00Z")
            
        content_text = f"{subject}\n{body}"
        from services.triage_service import classify_grievance_heuristic, calculate_priority_heuristic
        
        # Apply the fast heuristic engine as the initial baseline
        initial_category = classify_grievance_heuristic(content_text, subject, user_email=USER_EMAIL)
        initial_priority = calculate_priority_heuristic(content_text, subject, user_email=USER_EMAIL)
        
        email_record = {
            "email_id": stable_id,
            "gmail_id": None,
            "thread_id": stable_id,  # Each PDF is a standalone thread
            "parent_email_id": None,
            "sender": f"{sender_name} <{sender_email}>",
            "sender_email": sender_email,
            "recipient_email": parsed.get("recipient_email", "techedndirectoratewb@gmail.com"),
            "subject": subject,
            "content": content_text,
            "category": initial_category,
            "mail_type": "fresh",
            "priority": initial_priority,
            "date": email_date,
            "has_attachment": True,
            "attachments": json.dumps([{
                "filename": pdf_path.name,
                "original_name": pdf_path.name,
                "size": pdf_path.stat().st_size
            }]),
            "is_demo": True,
            "replied": False,
            "is_trashed": False,
            "is_inbox": True,
            "is_sent": False,
            "is_ocr_processed": True, # Skip background OCR reading
            "attachment_content": f"[Extracted from PDF Email Import]\n\n{body[:1000]}...", # Satisfy UI badge
            "html_content": None,
            "to": parsed.get("to_full"),
            "cc": parsed.get("cc_full"),
            "followup_count": 0,
            "institute_name": None,
        }
        
        # Apply hardcoded triage if this is a demo email
        if stable_id in DEMO_TRIAGE_MAPPING:
            cat, prio = DEMO_TRIAGE_MAPPING[stable_id]
            email_record["category"] = cat
            email_record["priority"] = prio
            email_record["is_priority_refined"] = 1
            email_record["manual_override"] = 0
        
        emails_to_insert.append(email_record)
        

    
    # Step 4: Batch insert into DB
    if emails_to_insert:
        print(f"\n{'='*60}")
        print(f"[DB] Inserting {len(emails_to_insert)} emails into database...")
        save_emails_batch(USER_EMAIL, emails_to_insert)
        print(f"[OK] Successfully inserted {len(emails_to_insert)} emails!")
    
    if failed:
        print(f"\n[!] Failed to process {len(failed)} files:")
        for f in failed:
            print(f"   - {f}")
    
    # Step 5: Run AI Triage
    print(f"\n{'='*60}")
    print("[AI] Running AI triage for category & priority assignment...")
    try:
        from services.triage_llm import get_batch_triage
        
        # Process in larger batches for local LLM efficiency
        batch_size = 25
        total_triaged = 0
        
        for i in range(0, len(emails_to_insert), batch_size):
            batch = emails_to_insert[i:i+batch_size]
            
            # Filter out already triaged demo emails
            batch_to_refine = [e for e in batch if not e.get("manual_override")]
            if not batch_to_refine:
                continue
                
            triage_input = [{
                "id": e["email_id"],
                "sender": e["sender"],
                "subject": e["subject"],
                "content": e["content"][:700],
            } for e in batch_to_refine]
            
            results = get_batch_triage(triage_input, USER_EMAIL)
            
            if results:
                from db.session import get_db_conn
                with get_db_conn() as conn:
                    cursor = conn.cursor()
                    for eid, triage in results.items():
                        cursor.execute(
                            "UPDATE emails SET category = ?, priority = ?, is_priority_refined = 1 WHERE id = ? AND user_email = ?",
                            (triage["category"], triage["priority"], eid, USER_EMAIL)
                        )
                    conn.commit()
                total_triaged += len(results)
                print(f"  [OK] Triaged batch {i//batch_size + 1}: {len(results)} emails")
            
            time.sleep(2)  # Rate limit between batches
        
        print(f"🎯 Total triaged: {total_triaged}/{len(emails_to_insert)}")
    except Exception as e:
        print(f"[!] AI triage failed (can be run manually later): {e}")
    
    print(f"\n{'='*60}")
    print(f"[FINISH] Import complete!")
    print(f"   Total imported: {len(emails_to_insert)}")
    print(f"   User: {USER_EMAIL}")
    print(f"   Marked as: is_demo=True, is_inbox=True")


if __name__ == "__main__":
    import_all_pdfs()
