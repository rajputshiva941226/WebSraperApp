"""
Migration: widen master_database columns that cause StringDataRightTruncation.

  article_url  varchar(500) → TEXT
  author_name  varchar(255) → TEXT

Run once on the server:
  python migrate_master_db_columns.py
"""

from app import app
from models import db
import sys


def migrate():
    print("=" * 60)
    print("MIGRATION: widen master_database text columns")
    print("=" * 60)

    with app.app_context():
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)
        cols = {c['name']: c for c in inspector.get_columns('master_database')}

        changes = []

        # article_url: varchar(500) → TEXT
        url_col = cols.get('article_url', {})
        url_type = str(url_col.get('type', '')).upper()
        if 'TEXT' not in url_type:
            changes.append(
                "ALTER TABLE master_database ALTER COLUMN article_url TYPE TEXT"
            )
        else:
            print("  ✅ article_url is already TEXT — skipping")

        # author_name: varchar(255) → TEXT
        name_col = cols.get('author_name', {})
        name_type = str(name_col.get('type', '')).upper()
        if 'TEXT' not in name_type:
            changes.append(
                "ALTER TABLE master_database ALTER COLUMN author_name TYPE TEXT"
            )
        else:
            print("  ✅ author_name is already TEXT — skipping")

        if not changes:
            print("\nNothing to do — migration already applied.")
            return True

        for sql in changes:
            print(f"\n  Running: {sql}")
            try:
                db.session.execute(text(sql))
                db.session.commit()
                print("  ✅ Done")
            except Exception as exc:
                db.session.rollback()
                print(f"  ❌ Failed: {exc}")
                return False

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE — restart the app service now.")
    print("=" * 60)
    return True


if __name__ == '__main__':
    ok = migrate()
    sys.exit(0 if ok else 1)
