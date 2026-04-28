import os
from config import DB_PATH, DATA_DIR

print(f"DATA_DIR: {DATA_DIR}")
print(f"DB_PATH: {DB_PATH}")
print(f"DATA_DIR exists: {os.path.exists(DATA_DIR)}")
print(f"DB_PATH exists: {os.path.exists(DB_PATH)}")

if os.path.exists(DATA_DIR):
    print(f"Contents of DATA_DIR: {os.listdir(DATA_DIR)}")
