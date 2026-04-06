import sqlite3
import os

DB_PATH = "data/grievances.db"

def repair():
    if not os.path.exists(DB_PATH):
        print("DB not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Define standard mappings
    corrections = [
        ("Examination / Semester", "Semester / Examination"),
        ("Misc", "Miscellaneous"),
        ("miscellaneous", "Miscellaneous"),
        ("Others", "Miscellaneous"),
        ("other", "Miscellaneous")
    ]

    total_updated = 0
    for old, new in corrections:
        cursor.execute("UPDATE emails SET category = ? WHERE category = ?", (new, old))
        total_updated += cursor.rowcount
        if cursor.rowcount > 0:
            print(f"Updated {cursor.rowcount} rows: '{old}' -> '{new}'")

    conn.commit()
    print(f"Total rows repaired: {total_updated}")
    conn.close()

if __name__ == "__main__":
    repair()
