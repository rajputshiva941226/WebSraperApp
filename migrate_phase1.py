"""
Phase 1 DB migration: add stop_requested, worker_task_id, last_heartbeat_at to job table.
Run once on EC2: python3 migrate_phase1.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'journal_scraper.db')

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())

def run():
    print(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    migrations = [
        ("job", "stop_requested",    "INTEGER DEFAULT 0"),
        ("job", "worker_task_id",    "TEXT"),
        ("job", "last_heartbeat_at", "DATETIME"),
    ]

    for table, col, col_def in migrations:
        if column_exists(cur, table, col):
            print(f"  [skip]  {table}.{col} already exists")
        else:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            print(f"  [added] {table}.{col} {col_def}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    run()
