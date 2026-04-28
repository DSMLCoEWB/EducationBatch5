import sqlite3
import time
from db.repository import get_all_active_users
from core.coordination import trigger_intelligence_suite

def run_test():
    conn = sqlite3.connect('data/grievances.db')
    cursor = conn.cursor()
    
    # 1. Misclassify
    cursor.execute("UPDATE emails SET category='Anti-Ragging Complaints', is_priority_refined=0 WHERE subject LIKE '%SVMCMS%'")
    conn.commit()
    
    cursor.execute("SELECT subject, category, is_priority_refined FROM emails WHERE subject LIKE '%SVMCMS%'")
    print("--- AFTER INTENTIONAL MISCLASSIFICATION ---")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()

    # 2. Trigger AI worker
    print("\nTriggering AI worker...")
    users = get_all_active_users()
    for u in users:
        trigger_intelligence_suite(u)
        
    # 3. Wait for LLM (Poll DB)
    print("Waiting for LLM processing (up to 60s)...")
    for _ in range(60):
        conn = sqlite3.connect('data/grievances.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_priority_refined FROM emails WHERE subject LIKE '%SVMCMS%'")
        rows = cursor.fetchall()
        conn.close()
        
        if all(r[0] == 1 for r in rows):
            print("AI Processing Complete!")
            break
        time.sleep(1)
    
    # 4. Verify DB
    conn = sqlite3.connect('data/grievances.db')
    cursor = conn.cursor()
    cursor.execute("SELECT subject, category, is_priority_refined FROM emails WHERE subject LIKE '%SVMCMS%'")
    print("\n--- AFTER AI RECLASSIFICATION ---")
    for row in cursor.fetchall():
        print(row)
    conn.close()

if __name__ == '__main__':
    run_test()
