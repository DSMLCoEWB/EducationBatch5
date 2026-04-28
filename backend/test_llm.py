import sqlite3
from priority_llm import get_batch_triage

conn = sqlite3.connect('data/grievances.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM emails WHERE subject LIKE '%SVMCMS%'")
rows = [dict(r) for r in cursor.fetchall()]
conn.close()

if rows:
    res = get_batch_triage(rows)
    print("LLM Results:", res)
else:
    print('No rows found')
