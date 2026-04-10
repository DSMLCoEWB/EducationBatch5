import sqlite3
import sys
import os

# Add backend to path to import classifier
sys.path.append(r'd:\OneDrive\Desktop\Projects\AICOE_EDUCATION_with_priority\backend')
from classifier import classify_grievance

db_path = r'd:\OneDrive\Desktop\Projects\AICOE_EDUCATION_with_priority\backend\data\grievances.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Check ALL emails and their categories
cursor.execute("SELECT id, subject, category, is_inbox, is_trashed FROM emails WHERE is_inbox=1 AND is_trashed=0")
rows = cursor.fetchall()
print(f"Total Active Inbox Emails: {len(rows)}")

scholarship_count = 0
miscellaneous_count = 0
semester_count = 0

for r in rows:
    eid, subject, category, is_inbox, is_trashed = r
    if category == 'Scholarship':
        scholarship_count += 1
    elif category == 'Miscellaneous':
        miscellaneous_count += 1
    elif category == 'Semester / Examination':
        semester_count += 1

print(f"DB COUNTS: Scholarship={scholarship_count}, Miscellaneous={miscellaneous_count}, Semester={semester_count}")

# 2. Test the 8 Scholarship emails to see if they'd be reclassified by the current code
cursor.execute("SELECT id, subject, content, attachment_content, category FROM emails WHERE category='Scholarship'")
s_rows = cursor.fetchall()
print(f"\nAUDIT OF SCHOLARSHIP EMAILS:")
for r in s_rows:
    eid, sub, content, attach, cat = r
    new_cat = classify_grievance(content or '', sub or '', attach or '')
    print(f"ID: {eid} | Sub: {sub[:50]} | New Cat: {new_cat}")

conn.close()
