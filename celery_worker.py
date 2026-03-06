"""
Celery Worker — replaces Flask background threads for job execution.

Start worker on EC2:
    celery -A celery_worker worker --loglevel=info --concurrency=4

The Flask app submits tasks via .delay() / .apply_async().
Workers run scrapers independently of any HTTP request/session/login state.
"""

import os
import threading
import time
import glob
from datetime import datetime
from celery import Celery

# ------------------------------------------------------------------
# Celery app config — reads REDIS_URL env var (default: localhost)
# ------------------------------------------------------------------
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'journal_scraper',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # Re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1,  # One task per worker at a time (scrapers are heavy)
    task_soft_time_limit=3600,     # 1 hour soft limit
    task_time_limit=3900,          # Hard kill after 65 min
)


def _get_flask_app():
    """Import Flask app lazily to avoid circular imports."""
    from app import app
    return app


def _db_update(job_id, updates):
    """Update job row in DB safely from a Celery worker context."""
    flask_app = _get_flask_app()
    try:
        with flask_app.app_context():
            from models import db, Job
            db_job = Job.query.get(job_id)
            if db_job:
                for key, val in updates.items():
                    if hasattr(db_job, key):
                        if key in ('start_time', 'end_time', 'last_heartbeat_at') and isinstance(val, str):
                            try:
                                setattr(db_job, key, datetime.fromisoformat(val))
                            except Exception:
                                pass
                        else:
                            setattr(db_job, key, val)
                db.session.commit()
    except Exception as e:
        print(f"[CeleryWorker][DB] Failed to update job {job_id}: {e}")
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def _is_stop_requested(job_id):
    """Check DB for stop_requested flag."""
    flask_app = _get_flask_app()
    try:
        with flask_app.app_context():
            from models import Job
            db_job = Job.query.get(job_id)
            return bool(db_job and db_job.stop_requested)
    except Exception:
        return False


def count_results_detailed(filepath):
    """Count authors, emails, and links with unique counts."""
    try:
        if not filepath or not os.path.exists(filepath):
            return 0, 0, 0, 0, 0
        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            unique_authors = set()
            unique_emails = set()
            unique_links = set()
            total_rows = 0
            for row in reader:
                total_rows += 1
                author = row.get('Author_Name') or row.get('Name') or row.get('author_name') or ''
                if author and author.strip() and author.strip() != 'N/A':
                    unique_authors.add(author.strip().lower())
                email = row.get('Email') or row.get('email') or ''
                if email and '@' in email and email.strip() != 'N/A':
                    unique_emails.add(email.strip().lower())
                link = row.get('Article_URL') or row.get('URL') or row.get('Article URL') or ''
                if link and link.strip() and link.strip() != 'N/A':
                    unique_links.add(link.strip())
        return total_rows, len(unique_emails), len(unique_authors), len(unique_emails), len(unique_links)
    except Exception as e:
        print(f"[CeleryWorker] Error counting results: {e}")
        return 0, 0, 0, 0, 0


@celery_app.task(bind=True, name='celery_worker.run_scraper_task')
def run_scraper_task(self, job_id, user_id, journal, keyword, start_date, end_date,
                     conference_name='default', mesh_type='all'):
    """
    Celery task: runs a scraper job fully independently of Flask sessions.
    Survives user logout, server reload, gunicorn worker replacement.
    """
    flask_app = _get_flask_app()

    # Per-job isolated output directory
    upload_folder = flask_app.config.get('UPLOAD_FOLDER', 'results')
    job_output_dir = os.path.join(upload_folder, user_id, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    start_time = time.time()

    # ------------------------------------------------------------------
    # Heartbeat thread — updates DB every 15 s
    # ------------------------------------------------------------------
    _heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        while not _heartbeat_stop.is_set():
            _db_update(job_id, {'last_heartbeat_at': datetime.utcnow().isoformat()})
            _heartbeat_stop.wait(15)

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # ------------------------------------------------------------------
    # Progress callback — writes live progress to DB
    # ------------------------------------------------------------------
    def progress_callback(progress, status, current_url='', links_count=0,
                          authors_count=0, emails_count=0):
        if _is_stop_requested(job_id):
            raise KeyboardInterrupt('Job stopped by user')

        if progress % 5 == 0 or progress == 100:
            _db_update(job_id, {
                'progress': progress,
                'message': status,
                'current_url': current_url,
                'links_count': links_count,
                'authors_count': authors_count,
                'emails_count': emails_count,
                'last_heartbeat_at': datetime.utcnow().isoformat(),
            })
        print(f"[Celery][{job_id[:8]}] {progress}% - {status}")

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------
    try:
        _db_update(job_id, {
            'status': 'running',
            'start_time': datetime.utcnow().isoformat(),
            'progress': 0,
            'worker_task_id': self.request.id or job_id,
        })

        from scraper_adapter import ScraperAdapter
        
        # Only install ChromeDriver for Selenium-based scrapers
        # API scrapers (europepmc, pubmed) don't need Chrome
        api_scrapers = {'europepmc', 'pubmed'}
        driver_path = None
        
        if journal not in api_scrapers:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()

        with flask_app.app_context():
            adapter = ScraperAdapter(job_id=job_id, output_dir=job_output_dir)
            adapter.set_progress_callback(progress_callback)
            output_file, summary = adapter.run_scraper(
                scraper_type=journal,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                driver_path=driver_path,
                conference_name=conference_name,
                mesh_type=mesh_type
            )

        authors_count, emails_count, unique_authors, unique_emails, unique_links = \
            count_results_detailed(output_file)
        duration = time.time() - start_time
        msg = f'\u2713 Completed! Found {unique_authors} unique authors, {unique_emails} unique emails'

        _db_update(job_id, {
            'status': 'completed',
            'end_time': datetime.utcnow().isoformat(),
            'duration': duration,
            'output_file': output_file,
            'authors_count': authors_count,
            'emails_count': emails_count,
            'unique_authors': unique_authors,
            'unique_emails': unique_emails,
            'unique_links': unique_links,
            'progress': 100,
            'message': msg,
        })

    except KeyboardInterrupt:
        duration = time.time() - start_time
        _db_update(job_id, {
            'status': 'stopped',
            'end_time': datetime.utcnow().isoformat(),
            'duration': duration,
            'message': 'Job stopped by user',
            'progress': 0,
        })

    except Exception as e:
        duration = time.time() - start_time
        partial_output_file = None
        try:
            csv_files = glob.glob(os.path.join(job_output_dir, '*.csv'))
            if csv_files:
                partial_output_file = csv_files[0]
        except Exception:
            pass

        if partial_output_file:
            pa, pe, pua, pue, pul = count_results_detailed(partial_output_file)
            has_partial = pue > 0
            msg = (f'\u26a0\ufe0f Failed with partial results: {str(e)[:100]}... '
                   f'| Found {pue} emails, {pua} authors') if has_partial else f'\u2717 Failed: {str(e)}'
            _db_update(job_id, {
                'status': 'failed', 'end_time': datetime.utcnow().isoformat(),
                'duration': duration, 'error': str(e), 'progress': 0,
                'output_file': partial_output_file if has_partial else None,
                'authors_count': pa, 'emails_count': pe,
                'unique_authors': pua, 'unique_emails': pue, 'unique_links': pul,
                'has_partial_results': has_partial, 'message': msg,
            })
        else:
            msg = f'\u2717 Failed: {str(e)}'
            _db_update(job_id, {
                'status': 'failed', 'end_time': datetime.utcnow().isoformat(),
                'duration': duration, 'error': str(e), 'progress': 0,
                'has_partial_results': False, 'message': msg,
            })

    finally:
        _heartbeat_stop.set()
