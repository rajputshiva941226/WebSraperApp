"""
Database Migration Script - Add allowed_scrapers Column
Run this to update existing database with new features
"""

from app import app
from models import db
import sys

def migrate_database():
    """Add allowed_scrapers column to existing database"""
    print("=" * 60)
    print("DATABASE MIGRATION - Adding Scraper Permissions")
    print("=" * 60)
    
    try:
        with app.app_context():
            # Check if column already exists
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('user')]
            
            if 'allowed_scrapers' in columns:
                print("✅ Column 'allowed_scrapers' already exists!")
                print("   No migration needed.")
                return True
            
            print("\n📊 Adding 'allowed_scrapers' column to user table...")
            
            # Add the new column - SQLite syntax
            sql = "ALTER TABLE user ADD COLUMN allowed_scrapers TEXT DEFAULT 'all'"
            db.session.execute(db.text(sql))
            db.session.commit()
            
            print("✅ Successfully added 'allowed_scrapers' column!")
            
            # Set default value for existing users
            from models import User
            users = User.query.all()
            for user in users:
                if not user.allowed_scrapers:
                    user.allowed_scrapers = 'all'
            
            db.session.commit()
            print(f"✅ Updated {len(users)} existing users with default permissions")
            
            print("\n" + "=" * 60)
            print("MIGRATION COMPLETE!")
            print("=" * 60)
            print("\nNew Features Available:")
            print("  • Per-user scraper permissions")
            print("  • Admin can control which scrapers each user can access")
            print("  • Go to Admin Panel → Manage Scrapers")
            print("\nRestart your Flask server to apply changes.")
            print("=" * 60)
            
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR: Migration failed!")
        print(f"   {str(e)}")
        print("\nIf you see 'duplicate column' error, the migration already ran.")
        print("If you see other errors, you may need to recreate the database:")
        print("  1. Delete journal_scraper.db")
        print("  2. Run: python init_database.py")
        return False

if __name__ == '__main__':
    print("\nThis will add the 'allowed_scrapers' column to your database.")
    response = input("Continue? (y/n): ")
    
    if response.lower() == 'y':
        success = migrate_database()
        sys.exit(0 if success else 1)
    else:
        print("Migration cancelled.")
        sys.exit(0)
