import sqlite3
import os

db_path = r"d:\OneDrive\Desktop\Projects\AICOE_EDUCATION_with_priority\backend\data\grievances.db"

def get_schema():
    if not os.path.exists(db_path):
        print(f"Error: {db_path} does not exist.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema_info = {}
    for table_name in tables:
        t_name = table_name[0]
        cursor.execute(f"PRAGMA table_info({t_name});")
        columns = cursor.fetchall()
        schema_info[t_name] = columns
        
    conn.close()
    return schema_info

if __name__ == "__main__":
    schema = get_schema()
    for table, cols in schema.items():
        print(f"Table: {table}")
        for col in cols:
            print(f"  Column: {col[1]} ({col[2]})")
