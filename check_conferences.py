"""
Diagnostic script to check if conferences are in the database
"""

from app import app, db
from models import Conference, User

def check_conferences():
    """Check conferences in database"""
    with app.app_context():
        print("\n" + "="*60)
        print("CONFERENCE DATABASE CHECK")
        print("="*60)
        
        # Count total conferences
        total = Conference.query.count()
        print(f"\nTotal conferences in database: {total}")
        
        if total == 0:
            print("⚠️  No conferences found!")
            return
        
        # List all conferences
        print("\nConferences:")
        print("-" * 60)
        conferences = Conference.query.order_by(Conference.name).all()
        
        for i, conf in enumerate(conferences, 1):
            print(f"\n{i}. {conf.name}")
            print(f"   ID: {conf.id}")
            print(f"   Short Form: {conf.short_form}")
            print(f"   Display Name: {conf.display_name}")
            print(f"   Active: {conf.is_active}")
            print(f"   Created: {conf.created_at}")
            
            # Check assigned users
            assigned_users = conf.assigned_users.all()
            print(f"   Assigned Users: {len(assigned_users)}")
            for user in assigned_users:
                print(f"      - {user.username} ({user.email})")
        
        print("\n" + "="*60)
        print("USERS IN DATABASE")
        print("="*60)
        
        users = User.query.all()
        print(f"\nTotal users: {len(users)}")
        
        for user in users:
            assigned_confs = user.assigned_conferences.all()
            print(f"\n{user.username} ({user.user_type})")
            print(f"   Email: {user.email}")
            print(f"   Assigned Conferences: {len(assigned_confs)}")
            for conf in assigned_confs:
                print(f"      - {conf.name}")
        
        print("\n" + "="*60)

if __name__ == '__main__':
    check_conferences()
