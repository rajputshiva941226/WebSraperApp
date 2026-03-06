"""
Debug: show all users and their job counts to diagnose filtering issue.
Run: python3 debug_jobs.py
"""
from app import app
from models import db, User, Job

with app.app_context():
    users = User.query.all()
    print("=== USERS ===")
    for u in users:
        job_count = Job.query.filter_by(user_id=u.id).count()
        print(f"  {u.username} | id={u.id} | type={u.user_type} | jobs={job_count}")

    print("\n=== JOBS (first 10) ===")
    jobs = Job.query.order_by(Job.created_at.desc()).limit(10).all()
    for j in jobs:
        print(f"  job_id={j.id[:8]}... | user_id={j.user_id} | journal={j.journal} | status={j.status}")

    print("\n=== NULL user_id jobs ===")
    null_jobs = Job.query.filter(Job.user_id == None).count()
    print(f"  Count: {null_jobs}")

    total = Job.query.count()
    print(f"\n=== TOTAL JOBS: {total} ===")
