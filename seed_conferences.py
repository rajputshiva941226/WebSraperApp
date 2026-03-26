"""
Seed script to populate conferences with short form mappings
Run this once to initialize all conferences in the database
"""

import sys
from app import app, db
from models import Conference
from conference_config import CONFERENCE_MAPPINGS
from datetime import datetime
import uuid


def seed_conferences():
    """Populate database with all conferences from the mapping"""
    with app.app_context():
        # Check if conferences already exist
        existing_count = Conference.query.count()
        if existing_count > 0:
            print(f"⚠️  Database already contains {existing_count} conferences. Skipping seed.")
            return
        
        print("🌱 Seeding conferences...")
        created_count = 0
        
        for short_form, full_form in CONFERENCE_MAPPINGS.items():
            try:
                conference = Conference(
                    id=str(uuid.uuid4()),
                    name=full_form,
                    short_form=short_form,
                    display_name=full_form,
                    description=f"Conference: {full_form}",
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.session.add(conference)
                created_count += 1
                print(f"  ✓ {short_form:6} → {full_form}")
            except Exception as e:
                print(f"  ✗ Error creating {short_form}: {e}")
                db.session.rollback()
                continue
        
        try:
            db.session.commit()
            print(f"\n✅ Successfully seeded {created_count} conferences!")
        except Exception as e:
            print(f"\n❌ Error committing conferences: {e}")
            db.session.rollback()


if __name__ == '__main__':
    seed_conferences()
