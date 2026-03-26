"""
Simple database check without Flask dependencies
"""

import sqlite3
import os

def check_database():
    """Check SQLite database for conferences"""
    db_path = 'instance/journal_scraper.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n" + "="*70)
        print("DATABASE CONFERENCE CHECK")
        print("="*70)
        
        # Check if conference table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conference'")
        if not cursor.fetchone():
            print("❌ Conference table does not exist!")
            conn.close()
            return
        
        # Count conferences
        cursor.execute("SELECT COUNT(*) FROM conference")
        count = cursor.fetchone()[0]
        print(f"\n✓ Total conferences in database: {count}")
        
        if count == 0:
            print("⚠️  No conferences found in database!")
            conn.close()
            return
        
        # List all conferences
        print("\nConferences:")
        print("-" * 70)
        cursor.execute("""
            SELECT id, name, short_form, display_name, is_active, created_at 
            FROM conference 
            ORDER BY name
        """)
        
        conferences = cursor.fetchall()
        for i, (conf_id, name, short_form, display_name, is_active, created_at) in enumerate(conferences, 1):
            print(f"\n{i}. {name}")
            print(f"   ID: {conf_id}")
            print(f"   Short Form: {short_form}")
            print(f"   Display Name: {display_name}")
            print(f"   Active: {is_active}")
            print(f"   Created: {created_at}")
        
        # Check user_conference association table
        print("\n" + "="*70)
        print("USER-CONFERENCE ASSIGNMENTS")
        print("="*70)
        
        cursor.execute("SELECT COUNT(*) FROM user_conference")
        assignment_count = cursor.fetchone()[0]
        print(f"\nTotal user-conference assignments: {assignment_count}")
        
        if assignment_count > 0:
            cursor.execute("""
                SELECT u.username, c.name 
                FROM user_conference uc
                JOIN users u ON uc.user_id = u.id
                JOIN conference c ON uc.conference_id = c.id
                ORDER BY u.username, c.name
            """)
            
            assignments = cursor.fetchall()
            print("\nAssignments:")
            for username, conf_name in assignments:
                print(f"  - {username} → {conf_name}")
        
        # Check users table
        print("\n" + "="*70)
        print("USERS IN DATABASE")
        print("="*70)
        
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"\nTotal users: {user_count}")
        
        cursor.execute("SELECT id, username, email, user_type FROM users ORDER BY username")
        users = cursor.fetchall()
        
        for user_id, username, email, user_type in users:
            print(f"\n{username} ({user_type})")
            print(f"  Email: {email}")
            print(f"  ID: {user_id}")
            
            # Get assigned conferences for this user
            cursor.execute("""
                SELECT c.name FROM user_conference uc
                JOIN conference c ON uc.conference_id = c.id
                WHERE uc.user_id = ?
                ORDER BY c.name
            """, (user_id,))
            
            assigned = cursor.fetchall()
            if assigned:
                print(f"  Assigned Conferences: {len(assigned)}")
                for (conf_name,) in assigned:
                    print(f"    - {conf_name}")
            else:
                print(f"  Assigned Conferences: 0")
        
        print("\n" + "="*70)
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_database()
