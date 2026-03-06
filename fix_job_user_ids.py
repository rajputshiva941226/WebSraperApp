"""
One-time migration: assign jobs with NULL user_id to the pritam admin user.
Run once on EC2: python3 fix_job_user_ids.py
"""
from app import app
from models import db, User, Job

with app.app_context():
    pritam = User.query.filter_by(username='pritam').first()
    if not pritam:
        print("ERROR: 'pritam' user not found. Check username.")
        exit(1)

    orphaned = Job.query.filter(Job.user_id == None).all()
    print(f"Found {len(orphaned)} jobs with NULL user_id -> assigning to '{pritam.username}' ({pritam.id})")

    for job in orphaned:
        job.user_id = pritam.id

    db.session.commit()
    print("Done. All orphaned jobs now assigned to pritam.")

    # Verify
    still_null = Job.query.filter(Job.user_id == None).count()
    print(f"Jobs still with NULL user_id: {still_null}")
