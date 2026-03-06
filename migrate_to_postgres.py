"""
Full data migration: SQLite → PostgreSQL

Usage on EC2:
    1. Install PostgreSQL and create the DB:
           sudo apt install postgresql postgresql-contrib -y
           sudo -u postgres psql -c "CREATE USER scraper_user WITH PASSWORD 'your_password';"
           sudo -u postgres psql -c "CREATE DATABASE journal_scraper OWNER scraper_user;"

    2. Install psycopg2:
           pip install psycopg2-binary

    3. Set env vars:
           export SQLITE_PATH=/var/www/journal-scraper/instance/journal_scraper.db
           export DATABASE_URL=postgresql://scraper_user:your_password@localhost/journal_scraper

    4. Run migration:
           python3 migrate_to_postgres.py

    5. After verifying data, set DATABASE_URL in /etc/systemd/system/journal-scraper.service
       and restart:
           sudo systemctl daemon-reload
           sudo systemctl restart journal-scraper
"""

import os
import sys
import sqlite3
from datetime import datetime

SQLITE_PATH = os.environ.get('SQLITE_PATH', 'instance/journal_scraper.db')
PG_URL = os.environ.get('DATABASE_URL', '')

if not PG_URL or 'postgresql' not in PG_URL:
    print("ERROR: Set DATABASE_URL=postgresql://user:pass@host/dbname before running.")
    sys.exit(1)

if not os.path.exists(SQLITE_PATH):
    print(f"ERROR: SQLite DB not found at {SQLITE_PATH}")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def sqlite_rows(sqlite_path, table):
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def sqlite_tables(sqlite_path):
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return tables


def coerce_bool(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    return bool(int(val))


def coerce_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


# ---------------------------------------------------------------
# Create all PostgreSQL tables via SQLAlchemy models
# ---------------------------------------------------------------

def create_pg_schema():
    print("\n[1/5] Creating PostgreSQL schema via SQLAlchemy models...")
    # Temporarily override DATABASE_URL so Flask app uses PG
    os.environ['DATABASE_URL'] = PG_URL
    from app import app
    from models import db
    with app.app_context():
        db.create_all()
    print("      Schema created.")


# ---------------------------------------------------------------
# Per-table migration
# ---------------------------------------------------------------

BOOL_COLS = {
    'users': ['is_active', 'is_verified'],
    'job': ['has_partial_results', 'stop_requested'],
}

DT_COLS = {
    'users': ['created_at', 'last_login'],
    'job': ['created_at', 'start_time', 'end_time', 'last_heartbeat_at'],
    'downloads': ['downloaded_at'],
    'credit_transactions': ['created_at'],
    'master_database': ['scraped_date', 'created_at', 'updated_at'],
    'conference_master': ['upload_date', 'created_at'],
    'search_history': ['searched_at'],
}


def migrate_table(pg_conn, table, rows):
    if not rows:
        print(f"      {table}: 0 rows (skip)")
        return

    cur = pg_conn.cursor()
    cols = list(rows[0].keys())
    bool_cols = BOOL_COLS.get(table, [])
    dt_cols_for_table = DT_COLS.get(table, [])

    coerced = []
    for row in rows:
        r = dict(row)
        for c in bool_cols:
            if c in r:
                r[c] = coerce_bool(r[c])
        for c in dt_cols_for_table:
            if c in r:
                r[c] = coerce_dt(r[c])
        coerced.append(tuple(r[c] for c in cols))

    placeholders = ','.join(['%s'] * len(cols))
    col_str = ','.join(f'"{c}"' for c in cols)

    try:
        execute_values(
            cur,
            f'INSERT INTO "{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING',
            coerced,
            template=f'({placeholders})',
            page_size=500,
        )
        pg_conn.commit()
        print(f"      {table}: {len(rows)} rows migrated")
    except Exception as e:
        pg_conn.rollback()
        print(f"      {table}: ERROR — {e}")


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main():
    print("=" * 60)
    print("  SQLite → PostgreSQL Migration")
    print(f"  Source:      {SQLITE_PATH}")
    print(f"  Destination: {PG_URL.split('@')[-1]}")
    print("=" * 60)

    # Step 1: create schema
    create_pg_schema()

    # Step 2: connect to PG
    print("\n[2/5] Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(PG_URL)
    print("      Connected.")

    # Step 3: discover tables in SQLite
    print("\n[3/5] Reading SQLite tables...")
    tables = sqlite_tables(SQLITE_PATH)
    print(f"      Found tables: {tables}")

    # Step 4: migrate each table in dependency order
    ORDER = [
        'users',
        'credit_transactions',
        'downloads',
        'master_database',
        'conference_master',
        'job',
        'search_history',
    ]
    # Add any tables not in ORDER at the end
    for t in tables:
        if t not in ORDER:
            ORDER.append(t)

    print("\n[4/5] Migrating data...")
    for table in ORDER:
        if table not in tables:
            continue
        rows = sqlite_rows(SQLITE_PATH, table)
        migrate_table(pg_conn, table, rows)

    pg_conn.close()

    # Step 5: verify
    print("\n[5/5] Verifying row counts...")
    os.environ['DATABASE_URL'] = PG_URL
    from app import app
    from models import db, User, Job as JobModel
    with app.app_context():
        pg_users = User.query.count()
        pg_jobs = JobModel.query.count()
    sqlite_users = len(sqlite_rows(SQLITE_PATH, 'users'))
    sqlite_jobs = len(sqlite_rows(SQLITE_PATH, 'job'))
    print(f"      users:  SQLite={sqlite_users}  PostgreSQL={pg_users}")
    print(f"      jobs:   SQLite={sqlite_jobs}  PostgreSQL={pg_jobs}")

    if pg_users == sqlite_users and pg_jobs == sqlite_jobs:
        print("\n[OK] Migration successful! All rows match.")
    else:
        print("\n[WARN] Row counts differ — check errors above.")

    print("\nNext steps:")
    print("  1. Edit /etc/systemd/system/journal-scraper.service")
    print(f"     Add: Environment=DATABASE_URL={PG_URL}")
    print("  2. sudo systemctl daemon-reload")
    print("  3. sudo systemctl restart journal-scraper")
    print("  4. Test the app, then remove the SQLite file if all looks good.")


if __name__ == '__main__':
    main()
