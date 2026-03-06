"""
Simple Database Migration - Add allowed_scrapers Column
"""

import sqlite3
import os

# Database is in instance folder by default
DB_PATH = os.path.join('instance', 'journal_scraper.db')

def migrate():
    """Add allowed_scrapers column to user table"""
    
    if not os.path.exists(DB_PATH):
        print("❌ ERROR: Database file 'journal_scraper.db' not found!")
        print("   Run 'python init_database.py' first to create the database.")
        return False
    
    print("=" * 60)
    print("DATABASE MIGRATION - Adding Scraper Permissions")
    print("=" * 60)
    
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if column already exists (table name is 'users' not 'user')
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'allowed_scrapers' in columns:
            print("\n✅ Column 'allowed_scrapers' already exists!")
            print("   No migration needed.")
            conn.close()
            return True
        
        print("\n📊 Adding 'allowed_scrapers' column to users table...")
        
        # Add the column with default value
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN allowed_scrapers TEXT DEFAULT 'all'
        """)
        
        # Update existing users to have 'all' permissions
        cursor.execute("""
            UPDATE users 
            SET allowed_scrapers = 'all' 
            WHERE allowed_scrapers IS NULL
        """)
        
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'allowed_scrapers' in columns:
            print("✅ Successfully added 'allowed_scrapers' column!")
            
            # Count updated users
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"✅ Updated {user_count} existing user(s) with default permissions")
            
            print("\n" + "=" * 60)
            print("MIGRATION COMPLETE!")
            print("=" * 60)
            print("\n✨ New Features Now Available:")
            print("  • Per-user scraper permissions")
            print("  • Admin can control which scrapers each user can access")
            print("  • Go to Admin Panel → Click 🔧 Scrapers button")
            print("\n🚀 Restart your Flask server to apply changes:")
            print("   py app.py")
            print("=" * 60)
            
            conn.close()
            return True
        else:
            print("❌ ERROR: Column was not added successfully")
            conn.close()
            return False
            
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print("\n✅ Column already exists (duplicate column error)")
            print("   Migration already completed previously.")
            return True
        else:
            print(f"\n❌ ERROR: {str(e)}")
            print("\nTroubleshooting:")
            print("  1. Make sure journal_scraper.db exists")
            print("  2. Make sure no other program has the database open")
            print("  3. If issues persist, recreate database:")
            print("     - Delete journal_scraper.db")
            print("     - Run: python init_database.py")
            return False
    
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {str(e)}")
        print(f"   Type: {type(e).__name__}")
        return False
    
    finally:
        try:
            conn.close()
        except:
            pass

if __name__ == '__main__':
    print("\n⚠️  This will add the 'allowed_scrapers' column to your database.")
    print("   Your existing data will NOT be affected.\n")
    
    response = input("Continue? (y/n): ")
    
    if response.lower() == 'y':
        success = migrate()
        if success:
            print("\n✅ Migration successful! Restart your Flask server.")
        else:
            print("\n❌ Migration failed. See errors above.")
        exit(0 if success else 1)
    else:
        print("\n❌ Migration cancelled.")
        exit(0)
