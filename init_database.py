"""
Database Initialization Script
Run this once to create all tables and admin user
"""

from app import app
from models import db, create_admin_user
import sys

def init_database():
    """Initialize database with tables and admin user"""
    
    print("=" * 70)
    print("DATABASE INITIALIZATION")
    print("=" * 70)
    
    with app.app_context():
        print("\n1. Creating database tables...")
        try:
            db.create_all()
            print("   ✅ Tables created successfully!")
        except Exception as e:
            print(f"   ❌ Error creating tables: {e}")
            sys.exit(1)
        
        print("\n2. Creating admin user...")
        admin_username = input("   Enter admin username (default: admin): ").strip() or "admin"
        admin_email = input("   Enter admin email (default: admin@example.com): ").strip() or "admin@example.com"
        admin_password = input("   Enter admin password (default: admin123): ").strip() or "admin123"
        
        try:
            admin_user = create_admin_user(admin_username, admin_email, admin_password)
            print(f"   ✅ Admin user created: {admin_user.username}")
            print(f"   📧 Email: {admin_user.email}")
            print(f"   💳 Credits: {admin_user.credits}")
        except Exception as e:
            print(f"   ⚠️  Admin user may already exist or error: {e}")
        
        print("\n" + "=" * 70)
        print("DATABASE INITIALIZATION COMPLETE!")
        print("=" * 70)
        print(f"""
Next Steps:
1. Start the Flask server: py app.py
2. Login with admin credentials:
   - Username: {admin_username}
   - Password: {admin_password}
3. Create additional users via /register
4. Access credit management at /credits/manage (admin only)

Database file: journal_scraper.db
""")
        print("=" * 70)

if __name__ == "__main__":
    init_database()
