"""
Enhanced Journal Scraper Web Server
Aligned with requirements document but simplified (no DB yet)
Features: Dashboard, Metrics, Multi-journal support, Job tracking
"""

import os
import json
import threading
import time
import signal
import atexit
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from werkzeug.utils import secure_filename
import uuid
from collections import defaultdict
import pandas as pd
from models import db, init_db, Job
from auth_routes import auth_bp
from credit_routes import credit_bp
from master_db_routes import master_db_bp
from admin_routes import admin_bp
from flask_login import LoginManager

# Celery integration — used when REDIS_URL is set, else falls back to threads
_USE_CELERY = bool(os.environ.get('REDIS_URL'))
if _USE_CELERY:
    try:
        from celery_worker import run_scraper_task as _celery_run_scraper, SELENIUM_SCRAPERS, API_SCRAPERS
        print("[Celery] Redis found — jobs will run via Celery workers")
    except ImportError:
        _USE_CELERY = False
        print("[Celery] celery_worker import failed — falling back to threads")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production')
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'results')
app.config['DATA_FOLDER'] = os.environ.get('DATA_FOLDER', 'data')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Database configuration — reads DATABASE_URL env var.
# On EC2 set: export DATABASE_URL=postgresql://user:pass@localhost/journal_scraper
# Falls back to SQLite for local dev.
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///journal_scraper.db')
# Heroku/render compat: fix legacy postgres:// scheme
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
# PostgreSQL connection pool settings (ignored by SQLite)
if 'postgresql' in _db_url:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

# Initialize database
init_db(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(credit_bp)
app.register_blueprint(master_db_bp)
app.register_blueprint(admin_bp)


# Create required directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)
os.makedirs('logs', exist_ok=True)

# In-memory storage (will be replaced with database later)
active_jobs = {}
job_history = []
job_threads = {}  # Track threads for job control
job_stop_flags = {}  # Flag to stop job execution
journal_metrics = defaultdict(lambda: {
    'total_jobs': 0,
    'successful_jobs': 0,
    'failed_jobs': 0,
    'total_authors_extracted': 0,
    'total_emails_extracted': 0,
    'avg_processing_time': 0,
    'last_run': None
})

# Journal configurations
JOURNALS = {
    'bmj': {
        'name': 'BMJ Journals',
        'full_name': 'British Medical Journal',
        'type': 'selenium',
        'enabled': True,
        #'icon': '🏥',
        'description': 'Leading medical journal publishing research and education'
    },
    'cambridge': {
        'name': 'Cambridge University Press',
        'full_name': 'Cambridge Academic Journals',
        'type': 'selenium',
        'enabled': True,
        #'icon': '🎓',
        'description': 'Academic publishing from Cambridge University'
    },
    'europepmc': {
        'name': 'Europe PMC',
        'full_name': 'Europe PubMed Central',
        'type': 'api',
        'enabled': True,
        #'icon': '🔬',
        'description': 'Open access database of life sciences literature'
    },
    'nature': {
        'name': 'Nature',
        'full_name': 'Nature Publishing',
        'type': 'selenium',
        'enabled': True,
        #'icon': '🌿',
        'description': 'Multidisciplinary scientific journal'
    },
    'springer': {
        'name': 'Springer',
        'full_name': 'Springer Academic Journals',
        'type': 'selenium',
        'enabled': True,
        #'icon': '📚',
        'description': 'International scientific publishing company'
    },
    'oxford': {
        'name': 'Oxford Academic',
        'full_name': 'Oxford University Press Journals',
        'type': 'selenium',
        'enabled': True,
        #'icon': '📖',
        'description': 'Academic journals from Oxford University Press'
    },
    'lippincott': {
        'name': 'Lippincott',
        'full_name': 'Lippincott Williams & Wilkins',
        'type': 'selenium',
        'enabled': True,
        #'icon': '⚕️',
        'description': 'Medical and nursing publications'
    },
    'sage': {
        'name': 'SAGE Journals',
        'full_name': 'SAGE Publications',
        'type': 'selenium',
        'enabled': True,
        #'icon': '📝',
        'description': 'Social science and humanities research'
    },
    'emerald': {
        'name': 'Emerald Insight',
        'full_name': 'Emerald Publishing',
        'type': 'selenium',
        'enabled': True,
        #'icon': '💎',
        'description': 'Management and business research journals'
    },
    'mdpi': {
        'name': 'MDPI',
        'full_name': 'MDPI Journals',
        'type': 'selenium',
        'enabled': True,
        #'icon': '🧬',
        'description': 'Open access scientific publisher'
    },
    'pubmed': {
        'name': 'PubMed',
        'full_name': 'PubMed Central',
        'type': 'api',
        'enabled': True,
        #'icon': '🧬',
        'description': 'Open access scientific publisher'
    },
    'tandf': {
        'name': 'TandFonline',
        'full_name': 'Taylor and Francis',
        'type': 'selenium',
        'enabled': True,
        'description': 'Multidisciplinary academic journals publisher'
    },
    'wiley': {
        'name': 'OnlineWiley',
        'full_name': 'Online Wiley',
        'type': 'selenium',
        'enabled': True,
        'description': 'Scientific, technical, and medical research journals'
    },
    'sciencedirect': {
        'name': 'Science Direct',
        'full_name': 'Science Direct',
        'type': 'selenium',
        'enabled': True,
        'description': 'Elsevier scientific research journals'
    },
    'pdf_scraper': {
        'name': 'PDF Scraper',
        'full_name': 'PDF Author Email Extractor',
        'type': 'selenium',
        'enabled': True,
        'description': 'Extract author emails from uploaded PDF files'
    }
}

# Load persisted data
def load_metrics():
    """Load metrics from disk"""
    global journal_metrics, job_history
    try:
        metrics_file = os.path.join(app.config['DATA_FOLDER'], 'metrics.json')
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r') as f:
                data = json.load(f)
                journal_metrics.update(data.get('journal_metrics', {}))
                job_history = data.get('job_history', [])
    except Exception as e:
        print(f"Error loading metrics: {e}")

def save_metrics():
    """Save metrics to disk"""
    try:
        metrics_file = os.path.join(app.config['DATA_FOLDER'], 'metrics.json')
        with open(metrics_file, 'w') as f:
            json.dump({
                'journal_metrics': dict(journal_metrics),
                'job_history': job_history[-1000:]  # Keep last 1000 jobs
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving metrics: {e}")

def update_journal_metrics(journal, job_data):
    """Update metrics for a journal after job completion"""
    metrics = journal_metrics[journal]
    metrics['total_jobs'] += 1
    
    if job_data['status'] == 'completed':
        metrics['successful_jobs'] += 1
        metrics['total_authors_extracted'] += job_data.get('authors_count', 0)
        metrics['total_emails_extracted'] += job_data.get('emails_count', 0)
        
        # Update average processing time
        duration = job_data.get('duration', 0)
        current_avg = metrics['avg_processing_time']
        metrics['avg_processing_time'] = (
            (current_avg * (metrics['successful_jobs'] - 1) + duration) / 
            metrics['successful_jobs']
        )
    elif job_data['status'] == 'failed':
        metrics['failed_jobs'] += 1
    
    metrics['last_run'] = datetime.now().isoformat()
    save_metrics()

def _db_update(job_id, updates):
    """Update a job row in DB from a background thread safely."""
    try:
        with app.app_context():
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
        print(f"[DB] Failed to update job {job_id}: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass


def _is_stop_requested(job_id):
    """Check DB for stop_requested flag (DB is source of truth)."""
    # Also honour in-memory flag (set immediately by stop endpoint)
    if job_stop_flags.get(job_id, False):
        return True
    try:
        with app.app_context():
            db_job = Job.query.get(job_id)
            if db_job and db_job.stop_requested:
                job_stop_flags[job_id] = True
                return True
    except Exception:
        pass
    return False


def run_scraper_task(job_id, user_id, journal, keyword, start_date, end_date,
                    conference_name='default', mesh_type='all', delay=0):
    """
    Background task for thread-based execution (fallback when Celery is not available).
    When Celery is enabled, this is NOT used — celery_worker.run_scraper_task is used instead.
    """
    # Per-job isolated output directory
    job_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], user_id, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    # Apply stagger delay
    if delay > 0:
        _db_update(job_id, {'message': f'Waiting {delay:.1f}s before starting...'})
        time.sleep(delay)

    start_time = time.time()

    # ------------------------------------------------------------------
    # Heartbeat: update DB every 15 s so stuck-job detection works
    # ------------------------------------------------------------------
    _heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        while not _heartbeat_stop.is_set():
            _db_update(job_id, {'last_heartbeat_at': datetime.utcnow().isoformat()})
            _heartbeat_stop.wait(15)

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # ------------------------------------------------------------------
    # Progress callback — writes to both cache and DB
    # ------------------------------------------------------------------
    def progress_callback(progress, status, current_url='', links_count=0,
                          authors_count=0, emails_count=0):
        if _is_stop_requested(job_id):
            raise KeyboardInterrupt('Job stopped by user')

        # Keep live cache for smooth UI polling
        if job_id in active_jobs:
            active_jobs[job_id].update({
                'progress': progress,
                'message': status,
                'current_url': current_url,
                'links_count': links_count,
                'authors_count': authors_count,
                'emails_count': emails_count,
            })

        # Persist to DB every ~5 progress points to avoid thrashing
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

        print(f"[{job_id}] {progress}% - {status}")

    # ------------------------------------------------------------------
    # Main scraper execution
    # ------------------------------------------------------------------
    try:
        _db_update(job_id, {
            'status': 'running',
            'start_time': datetime.utcnow().isoformat(),
            'progress': 0,
            'worker_task_id': str(threading.current_thread().ident),
        })
        if job_id in active_jobs:
            active_jobs[job_id].update({'status': 'running', 'progress': 0})

        from scraper_adapter import ScraperAdapter
        
        # Only install ChromeDriver for Selenium-based scrapers
        # API scrapers (europepmc, pubmed) don't need Chrome
        api_scrapers = {'europepmc', 'pubmed'}
        driver_path = None
        
        if journal not in api_scrapers:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()

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

        if job_id in active_jobs:
            active_jobs[job_id].update({
                'status': 'completed', 'progress': 100, 'message': msg,
                'output_file': output_file,
                'unique_authors': unique_authors, 'unique_emails': unique_emails,
            })

    except KeyboardInterrupt:
        # Cooperative stop
        duration = time.time() - start_time
        _db_update(job_id, {
            'status': 'stopped',
            'end_time': datetime.utcnow().isoformat(),
            'duration': duration,
            'message': 'Job stopped by user',
            'progress': 0,
        })
        if job_id in active_jobs:
            active_jobs[job_id].update({'status': 'stopped', 'message': 'Job stopped by user'})

    except Exception as e:
        duration = time.time() - start_time

        # Look for partial results in the per-job output dir
        partial_output_file = None
        try:
            import glob
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

        if job_id in active_jobs:
            active_jobs[job_id].update({'status': 'failed', 'message': msg})

    finally:
        _heartbeat_stop.set()
        # Clean up in-memory cache entry after a short delay (keep for UI polling)
        def _cleanup():
            time.sleep(30)
            active_jobs.pop(job_id, None)
            job_stop_flags.pop(job_id, None)
            job_threads.pop(job_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()


def count_results(filepath):
    """Count authors and emails in the result file"""
    try:
        if not filepath or not os.path.exists(filepath):
            return 0, 0
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) <= 1:  # Only header or empty
                return 0, 0
            
            # Count unique emails
            emails = set()
            for line in lines[1:]:  # Skip header
                parts = line.strip().split(',')
                if len(parts) > 1:  # Has email column
                    email = parts[1].strip().strip('"')
                    if email and '@' in email and email != 'N/A':
                        emails.add(email)
            
            authors_count = len(lines) - 1  # Total rows minus header
            emails_count = len(emails)
            
            return authors_count, emails_count
    except Exception as e:
        print(f"Error counting results: {e}")
        return 0, 0

def count_results_detailed(filepath):
    """Count authors, emails, and links with unique counts"""
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
                
                # Try multiple column name variations for author
                author = (row.get('Author_Name') or row.get('author_name') or 
                         row.get('full_name') or row.get('Name') or 
                         row.get('name') or row.get('first_name') or '')
                if author and author.strip() and author.strip().lower() != 'n/a':
                    unique_authors.add(author.strip().lower())
                
                # Try multiple column name variations for email
                email = (row.get('Email') or row.get('email') or 
                        row.get('Email_Address') or row.get('email_address') or '')
                if email and '@' in email and email.strip().lower() != 'n/a':
                    unique_emails.add(email.strip().lower())
                
                # Try multiple column name variations for URL/link
                # Check: Article_URL, URL, Article URL, pub_url, link, article_url, doi
                link = (row.get('Article_URL') or row.get('article_url') or 
                       row.get('URL') or row.get('url') or 
                       row.get('Article URL') or row.get('article url') or
                       row.get('pub_url') or row.get('pub_URL') or
                       row.get('link') or row.get('Link') or
                       row.get('doi') or row.get('DOI') or '')
                if link and link.strip() and link.strip().lower() != 'n/a':
                    unique_links.add(link.strip())
            
            return total_rows, len(unique_emails), len(unique_authors), len(unique_emails), len(unique_links)
    except Exception as e:
        print(f"Error counting detailed results: {e}")
        return 0, 0, 0, 0, 0

# Routes

@app.route('/')
def index():
    """Main landing page"""
    return render_template('landing.html', journals=JOURNALS)

@app.route('/scraper')
def scraper_page():
    """Scraping interface"""
    if 'user_id' not in session:
        from flask import flash
        return render_template('login.html', 
            error='Please login to access the scraper. Contact admin@email.com to create an account.')
    
    import json
    allowed_scrapers = session.get('allowed_scrapers', 'all')
    enabled_journals = {}
    for k, v in JOURNALS.items():
        if not v['enabled']:
            continue
        if allowed_scrapers == 'all':
            enabled_journals[k] = v
        else:
            try:
                allowed_list = json.loads(allowed_scrapers)
                if k in allowed_list:
                    enabled_journals[k] = v
            except Exception:
                enabled_journals[k] = v
    return render_template('scraper.html', journals=enabled_journals, allowed_scrapers=allowed_scrapers)

@app.route('/dashboard')
def dashboard():
    """Dashboard with metrics"""
    if 'user_id' not in session:
        return render_template('login.html',
            error='Please login to access the dashboard. Contact admin@email.com to create an account.')

    user_id = session.get('user_id')
    user_type = session.get('user_type', 'external')
    is_admin = (user_type == 'admin')

    # Pull stats from DB filtered by user (admins see all)
    try:
        from sqlalchemy import func
        base_q = Job.query if is_admin else Job.query.filter_by(user_id=user_id)
        total_jobs = base_q.count()
        total_successful = base_q.filter_by(status='completed').count() if is_admin else Job.query.filter_by(user_id=user_id, status='completed').count()
        total_failed = base_q.filter_by(status='failed').count() if is_admin else Job.query.filter_by(user_id=user_id, status='failed').count()
        author_q = db.session.query(func.sum(Job.unique_authors))
        email_q = db.session.query(func.sum(Job.unique_emails))
        if not is_admin:
            author_q = author_q.filter(Job.user_id == user_id)
            email_q = email_q.filter(Job.user_id == user_id)
        total_authors = author_q.scalar() or 0
        total_emails = email_q.scalar() or 0
        success_rate = (total_successful / total_jobs * 100) if total_jobs > 0 else 0
    except Exception:
        total_jobs = total_successful = total_failed = total_authors = total_emails = 0
        success_rate = 0

    # Get recent jobs filtered by user
    try:
        recent_q = Job.query if is_admin else Job.query.filter_by(user_id=user_id)
        db_recent = recent_q.order_by(Job.created_at.desc()).limit(10).all()
        db_recent_dicts = [j.to_dict() for j in db_recent]
    except Exception:
        db_recent_dicts = []

    # Merge with in-memory for live progress
    seen = set()
    recent_jobs = []
    for job in list(active_jobs.values()) + db_recent_dicts:
        jid = job.get('id')
        if jid and jid not in seen:
            if is_admin or job.get('user_id') == user_id:
                recent_jobs.append(job)
                seen.add(jid)
    recent_jobs = sorted(recent_jobs, key=lambda x: x.get('created_at', ''), reverse=True)[:10]

    # Active jobs count (user-filtered)
    active_count = len([j for j in active_jobs.values()
                        if j['status'] in ['pending', 'running']
                        and (is_admin or j.get('user_id') == user_id)])

    stats = {
        'total_jobs': total_jobs,
        'successful_jobs': total_successful,
        'failed_jobs': total_failed,
        'success_rate': round(success_rate, 1),
        'total_authors': total_authors,
        'total_emails': total_emails,
        'active_jobs': active_count
    }

    # Build per-user journal metrics from DB (not global in-memory which is shared across all users)
    try:
        from sqlalchemy import func as _func
        user_journal_metrics = {}
        for j_key in JOURNALS:
            jq = Job.query.filter_by(journal=j_key) if is_admin else Job.query.filter_by(journal=j_key, user_id=user_id)
            j_total = jq.count()
            j_success = jq.filter_by(status='completed').count()
            j_failed = jq.filter_by(status='failed').count() if is_admin else Job.query.filter_by(journal=j_key, user_id=user_id, status='failed').count()
            j_authors = (db.session.query(_func.sum(Job.unique_authors)).filter(Job.journal == j_key) if is_admin
                         else db.session.query(_func.sum(Job.unique_authors)).filter(Job.journal == j_key, Job.user_id == user_id)).scalar() or 0
            j_emails = (db.session.query(_func.sum(Job.unique_emails)).filter(Job.journal == j_key) if is_admin
                        else db.session.query(_func.sum(Job.unique_emails)).filter(Job.journal == j_key, Job.user_id == user_id)).scalar() or 0
            j_avg_time_q = (db.session.query(_func.avg(Job.duration)).filter(Job.journal == j_key, Job.status == 'completed') if is_admin
                            else db.session.query(_func.avg(Job.duration)).filter(Job.journal == j_key, Job.user_id == user_id, Job.status == 'completed'))
            j_avg_time = j_avg_time_q.scalar() or 0
            last_job = (Job.query.filter_by(journal=j_key) if is_admin else Job.query.filter_by(journal=j_key, user_id=user_id)
                        ).order_by(Job.created_at.desc()).first()
            user_journal_metrics[j_key] = {
                'total_jobs': j_total,
                'successful_jobs': j_success,
                'failed_jobs': j_failed,
                'total_authors_extracted': j_authors,
                'total_emails_extracted': j_emails,
                'avg_processing_time': round(j_avg_time / 60, 2) if j_avg_time else 0,
                'last_run': last_job.created_at.isoformat() if last_job and last_job.created_at else None
            }
    except Exception:
        user_journal_metrics = dict(journal_metrics)

    return render_template(
        'dashboard.html',
        journals=JOURNALS,
        journal_metrics=user_journal_metrics,
        stats=stats,
        recent_jobs=recent_jobs
    )

@app.route('/jobs')
def jobs_page():
    """Jobs management page"""
    if 'user_id' not in session:
        return render_template('login.html', 
            error='Please login to access jobs. Contact admin@email.com to create an account.')
    
    return render_template('jobs.html')

@app.route('/api/start-scraping', methods=['POST'])
def start_scraping():
    """Start scraping jobs — supports multiple journals."""
    try:
        data = request.get_json()

        journals = data.get('journals', [])
        if not journals and 'journal' in data:
            journals = [data['journal']]
        if not journals:
            return jsonify({'error': 'No journals selected'}), 400

        for journal in journals:
            if journal not in JOURNALS or not JOURNALS[journal]['enabled']:
                return jsonify({'error': f'Invalid or disabled journal: {journal}'}), 400

        conference_name = data.get('conference_name', 'default')
        mesh_type       = data.get('mesh_type', 'all')
        job_ids         = []
        user_id         = session.get('user_id')
        selenium_count  = 0

        for journal in journals:
            job_id = str(uuid.uuid4())
            job_ids.append(job_id)

            # ── FIX 1: Only populate active_jobs for thread-based execution.
            # With Celery, active_jobs causes split-brain across Gunicorn workers
            # because each process owns a separate copy of the dict.
            # The DB (written by the Celery worker via _db_update) is authoritative.
            if not _USE_CELERY:
                active_jobs[job_id] = {
                    'id':            job_id,
                    'user_id':       user_id,
                    'journal':       journal,
                    'journal_name':  JOURNALS[journal]['name'],
                    'keyword':       data['keyword'],
                    'conference':    conference_name,
                    'conference_name': conference_name,
                    'mesh_type':     mesh_type if journal == 'pubmed' else None,
                    'start_date':    data['start_date'],
                    'end_date':      data['end_date'],
                    'status':        'pending',
                    'created_at':    datetime.now().isoformat(),
                    'authors_count': 0,
                    'emails_count':  0,
                    'links_count':   0,
                    'unique_authors': 0,
                    'unique_emails':  0,
                    'unique_links':   0,
                    'current_url':   '',
                    'progress':      0,
                    'message':       'Job queued',
                    'paused':        False,
                }

            # Persist to DB — both Celery and thread paths need this
            try:
                db_job = Job(
                    id=job_id,
                    user_id=user_id,
                    journal=journal,
                    journal_name=JOURNALS[journal]['name'],
                    keyword=data['keyword'],
                    conference=conference_name,
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    mesh_type=mesh_type if journal == 'pubmed' else None,
                    status='pending',
                    progress=0,
                    message='Job queued',
                    created_at=datetime.utcnow(),
                )
                db.session.add(db_job)
                db.session.commit()
            except Exception as db_err:
                print(f"[DB] Failed to save job: {db_err}")
                db.session.rollback()

            job_stop_flags[job_id] = False

            # Stagger delay between selenium scrapers
            delay = 0
            if JOURNALS[journal]['type'] == 'selenium':
                if selenium_count > 0:
                    import random
                    delay = random.uniform(3, 5)
                selenium_count += 1

            if _USE_CELERY:
                # Route to the right queue so selenium/api workers can be
                # scaled independently:
                #   celery -A celery_worker worker -Q selenium --concurrency=2
                #   celery -A celery_worker worker -Q api      --concurrency=8
                queue = 'selenium' if journal in SELENIUM_SCRAPERS else 'api'
                task = _celery_run_scraper.apply_async(
                    args=(job_id, user_id, journal, data['keyword'],
                          data['start_date'], data['end_date'],
                          conference_name, mesh_type),
                    countdown=delay,
                    queue=queue,
                )
                # Write the Celery task ID back to DB so recover_stuck_jobs
                # can distinguish "Celery accepted" from "never started"
                try:
                    db_j = Job.query.get(job_id)
                    if db_j:
                        db_j.worker_task_id = task.id
                        db.session.commit()
                except Exception:
                    pass
            else:
                thread = threading.Thread(
                    target=run_scraper_task,
                    args=(job_id, user_id, journal, data['keyword'],
                          data['start_date'], data['end_date'],
                          conference_name, mesh_type, delay),
                )
                thread.daemon = True
                thread.start()
                job_threads[job_id] = thread
                if delay > 0:
                    time.sleep(delay)

        return jsonify({
            'success':  True,
            'job_ids':  job_ids,
            'message':  f'Started {len(job_ids)} scraping job(s) successfully',
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/jobs')
def list_jobs():
    """List jobs — DB is primary source; in-memory overlay only for threads."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id  = session.get('user_id')
    is_admin = (session.get('user_type', 'external') == 'admin')

    try:
        q       = Job.query if is_admin else Job.query.filter_by(user_id=user_id)
        db_jobs = q.order_by(Job.created_at.desc()).limit(200).all()
        result  = [j.to_dict() for j in db_jobs]
    except Exception as e:
        print(f"[DB] Error fetching jobs: {e}")
        result = []

    # ── FIX 2: Skip the in-memory overlay when Celery is active.
    # With multiple Gunicorn workers, active_jobs is inconsistent across
    # processes (each worker holds its own dict).  Overlaying it onto DB
    # data causes stale progress=0 / message="Job queued" to overwrite
    # fresh completed DB rows (the PubMed "0 emails" bug).
    # Celery workers write directly to DB, so DB is always current.
    if not _USE_CELERY:
        live_map = {jid: j for jid, j in active_jobs.items()
                    if is_admin or j.get('user_id') == user_id}
        for item in result:
            if item['id'] in live_map:
                live = live_map[item['id']]
                # Only overlay if the in-memory status is more recent
                # (i.e. the job is still actively running in this process)
                if live.get('status') in ('pending', 'running'):
                    item['progress']      = live.get('progress',      item.get('progress', 0))
                    item['message']       = live.get('message',        item.get('message', ''))
                    item['current_url']   = live.get('current_url',    item.get('current_url', ''))
                    item['authors_count'] = live.get('authors_count',  item.get('authors_count', 0))
                    item['emails_count']  = live.get('emails_count',   item.get('emails_count', 0))
                    item['links_count']   = live.get('links_count',    item.get('links_count', 0))

    return jsonify(result)


@app.route('/api/job-progress/<job_id>')
def job_progress(job_id):
    """Live progress for a single job — DB + optional thread overlay."""
    try:
        db_job = Job.query.get(job_id)
        if not db_job:
            return jsonify({'error': 'Job not found'}), 404
        data = db_job.to_dict()

        # ── FIX 2: Same guard as list_jobs — skip overlay for Celery jobs
        if not _USE_CELERY and job_id in active_jobs:
            live = active_jobs[job_id]
            if live.get('status') in ('pending', 'running'):
                data['progress']      = live.get('progress',      data.get('progress', 0))
                data['message']       = live.get('message',        data.get('message', ''))
                data['current_url']   = live.get('current_url',    data.get('current_url', ''))
                data['authors_count'] = live.get('authors_count',  data.get('authors_count', 0))
                data['emails_count']  = live.get('emails_count',   data.get('emails_count', 0))
                data['links_count']   = live.get('links_count',    data.get('links_count', 0))

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/job-status/<job_id>')
def job_status(job_id):
    """Compact status check — DB primary, thread overlay only when needed."""
    try:
        db_job = Job.query.get(job_id)
        if db_job:
            data = db_job.to_dict()
            # ── FIX 2: Celery jobs — DB is always authoritative
            if not _USE_CELERY and job_id in active_jobs:
                live = active_jobs[job_id]
                if live.get('status') in ('pending', 'running'):
                    data['progress']    = live.get('progress',    data.get('progress', 0))
                    data['message']     = live.get('message',     data.get('message', ''))
                    data['current_url'] = live.get('current_url', '')
            return jsonify(data)
    except Exception:
        pass
    return jsonify({'error': 'Job not found'}), 404

@app.route('/api/stop-job/<job_id>', methods=['POST'])
def stop_job(job_id):
    """Stop a running job - sets stop_requested flag in DB (cooperative stop)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    current_user_id = session.get('user_id')
    is_admin = session.get('user_type') == 'admin'

    try:
        db_job = Job.query.get(job_id)
        if not db_job:
            return jsonify({'error': 'Job not found'}), 404

        if not is_admin and db_job.user_id != current_user_id:
            return jsonify({'error': 'Access denied'}), 403

        if db_job.status not in ['running', 'pending']:
            return jsonify({'error': f'Job already {db_job.status}'}), 400

        # Set DB flag - worker checks this cooperatively
        db_job.stop_requested = True
        db_job.message = 'Stop requested...'
        db.session.commit()

        # Also set in-memory flag for immediate effect on current thread
        job_stop_flags[job_id] = True
        if job_id in active_jobs:
            active_jobs[job_id]['message'] = 'Stop requested...'

        return jsonify({'success': True, 'message': f'Stop requested for job {job_id}'})
    except Exception as e:
        print(f"[DB] Error stopping job: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<job_id>')
def download_results(job_id):
    """Download results for a specific job (CSV or XLSX)"""
    import pandas as pd
    from flask import request
    
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    current_user_id = session.get('user_id')
    is_admin = session.get('user_type') == 'admin'

    # Get format from query parameter (default to csv)
    format_type = request.args.get('format', 'csv').lower()
    
    # DB is sole source of truth
    try:
        db_job = Job.query.get(job_id)
        job = db_job.to_dict() if db_job else None
    except Exception:
        job = None

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if not is_admin and job.get('user_id') != current_user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Allow download for completed jobs OR failed jobs with partial results
    if job.get('status') not in ['completed', 'failed']:
        return jsonify({'error': 'Job not completed yet'}), 400
    
    # For failed jobs, check if partial results exist
    if job.get('status') == 'failed' and not job.get('has_partial_results'):
        return jsonify({'error': 'Job failed without producing results'}), 400
    
    output_file = job.get('output_file')
    results_dir = app.config.get('UPLOAD_FOLDER', 'results')
    job_user_id = job.get('user_id') or 'unknown'

    # Try to locate the file — check DB path first, then per-job dir, then flat results dir
    if not output_file or not os.path.exists(output_file):
        import glob as _glob
        candidates = []
        
        # If output_file is relative, make it absolute
        if output_file:
            if not os.path.isabs(output_file):
                output_file = os.path.join(results_dir, output_file)
            candidates.append(output_file)
            candidates.append(os.path.join(results_dir, os.path.basename(output_file)))
        
        # Phase-1 per-job dir (new structure: results/user_id/job_id/*.csv)
        candidates += _glob.glob(os.path.join(results_dir, job_user_id, job_id, '*.csv'))
        
        # Legacy flat dir (old structure: results/*.csv)
        journal_slug = (job.get('journal') or '').replace(' ', '_')
        candidates.append(os.path.join(results_dir, f"{job_id}_{journal_slug}_results.csv"))
        
        # Also search for any CSV with job_id in the filename
        candidates += _glob.glob(os.path.join(results_dir, f"{job_id}*.csv"))
        candidates += _glob.glob(os.path.join(results_dir, f"*{job_id}*.csv"))
        
        # Search recursively in results directory for this job_id
        candidates += _glob.glob(os.path.join(results_dir, '**', f"{job_id}*.csv"), recursive=True)

        output_file = next((p for p in candidates if p and os.path.exists(p)), None)

        if not output_file:
            return jsonify({'error': 'Output file not found on server'}), 404

    # Safe name components (guard against None)
    journal_name_safe = (job.get('journal_name') or job.get('journal') or 'results').replace(' ', '_')
    keyword_safe = (job.get('keyword') or 'unknown').replace(' ', '_')

    # If XLSX requested, generate it on-the-fly
    if format_type == 'xlsx':
        try:
            df = pd.read_csv(output_file)
            xlsx_path = output_file.replace('.csv', '.xlsx')
            
            # Ensure directory is writable
            try:
                os.chmod(os.path.dirname(xlsx_path), 0o777)
            except Exception:
                pass

            # Detect actual column names dynamically
            email_col = next((c for c in df.columns if c.lower() in ('email', 'emails', 'email_address')), None)
            author_col = next((c for c in df.columns if c.lower() in ('author_name', 'name', 'author', 'names')), None)
            url_col = next((c for c in df.columns if c.lower() in ('article_url', 'url', 'article url', 'link')), None)

            with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Results', index=False)
                stats_df = pd.DataFrame({
                    'Metric': ['Total Records', 'Unique Emails', 'Unique Authors',
                               'Unique URLs', 'Scraper', 'Keyword', 'Date Range', 'Completed At'],
                    'Value': [
                        len(df),
                        df[email_col].nunique() if email_col else job.get('unique_emails', 'N/A'),
                        df[author_col].nunique() if author_col else job.get('unique_authors', 'N/A'),
                        df[url_col].nunique() if url_col else job.get('unique_links', 'N/A'),
                        job.get('journal_name', 'Unknown'),
                        job.get('keyword', 'Unknown'),
                        f"{job.get('start_date', 'N/A')} to {job.get('end_date', 'N/A')}",
                        job.get('end_time', 'N/A'),
                    ]
                })
                stats_df.to_excel(writer, sheet_name='Statistics', index=False)
            
            # Ensure file is readable
            try:
                os.chmod(xlsx_path, 0o666)
            except Exception:
                pass

            return send_file(xlsx_path, as_attachment=True,
                             download_name=f"{journal_name_safe}_{keyword_safe}_results.xlsx")
        except Exception as e:
            return jsonify({'error': f'Failed to generate XLSX: {str(e)}'}), 500

    # Return CSV
    return send_file(output_file, as_attachment=True,
                     download_name=f"{journal_name_safe}_{keyword_safe}_results.csv")

@app.route('/api/download-bulk')
def download_bulk_results():
    """Download all completed job results as a zip file"""
    import zipfile
    import io

    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    current_user_id = session.get('user_id')
    is_admin = session.get('user_type') == 'admin'
    
    # DB is sole source of truth — no in-memory fallback needed
    try:
        q = Job.query.filter_by(status='completed') if is_admin \
            else Job.query.filter_by(status='completed', user_id=current_user_id)
        completed_jobs = [j.to_dict() for j in q.order_by(Job.created_at.desc()).limit(500).all()]
    except Exception as e:
        print(f"[DB] Error fetching completed jobs for bulk download: {e}")
        completed_jobs = []
    
    if not completed_jobs:
        return jsonify({'error': 'No completed jobs found'}), 404
    
    # Create zip file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for job in completed_jobs:
            output_file = job.get('output_file')
            if output_file and os.path.exists(output_file):
                # Use a descriptive filename
                filename = f"{job['journal']}_{job['keyword'].replace(' ', '_')}_results.csv"
                zip_file.write(output_file, filename)
    
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"bulk_scraping_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mimetype='application/zip'
    )

@app.route('/api/metrics')
def get_metrics():
    """Get all metrics"""
    return jsonify({
        'journal_metrics': dict(journal_metrics),
        'journals': JOURNALS
    })

@app.route('/api/metrics/<journal>')
def get_journal_metrics(journal):
    """Get metrics for a specific journal"""
    if journal not in JOURNALS:
        return jsonify({'error': 'Journal not found'}), 404
    
    return jsonify({
        'journal': journal,
        'journal_info': JOURNALS[journal],
        'metrics': journal_metrics.get(journal, {})
    })

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Clear job history (admin function)"""
    global job_history
    job_history = []
    save_metrics()
    return jsonify({'success': True, 'message': 'History cleared'})

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        active_count = Job.query.filter(Job.status.in_(['pending', 'running'])).count()
        db_ok = True
    except Exception:
        active_count = 0
        db_ok = False
    return jsonify({
        'status': 'healthy' if db_ok else 'degraded',
        'db': 'ok' if db_ok else 'error',
        'timestamp': datetime.now().isoformat(),
        'active_jobs': active_count,
        'total_journals': len(JOURNALS),
        'enabled_journals': len([j for j in JOURNALS.values() if j['enabled']])
    })

# Global flag to prevent duplicate cleanup
_cleanup_done = False
_cleanup_lock = threading.Lock()

# Cleanup function to stop all running jobs and close drivers
def cleanup_all_jobs():
    """Stop all running jobs and clean up resources"""
    global _cleanup_done
    
    # Prevent duplicate cleanup with thread-safe lock
    with _cleanup_lock:
        if _cleanup_done:
            return
        _cleanup_done = True
    
    # Only cleanup if there are actually jobs running
    active_count = len([j for j in active_jobs.values() if j['status'] in ['pending', 'running']])
    if active_count == 0:
        return  # Nothing to clean up
    
    print("\n\n" + "=" * 80)
    print("Shutting down gracefully...")
    print("=" * 80)
    
    # Stop all active jobs
    for job_id, job in list(active_jobs.items()):
        if job['status'] in ['pending', 'running']:
            print(f"Stopping job: {job['journal_name']} ({job_id[:8]}...)")
            job_stop_flags[job_id] = True
            job['status'] = 'stopped'
            job['message'] = 'Stopped by system shutdown'
    
    # Give threads a moment to stop
    time.sleep(2)
    
    # Force kill any remaining Chrome processes (Windows-specific)
    try:
        import subprocess
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], 
                      capture_output=True, timeout=5)
        subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe', '/T'], 
                      capture_output=True, timeout=5)
        print("✓ Cleaned up Chrome processes")
    except Exception as e:
        print(f"Note: Could not force-kill Chrome processes: {e}")
    
    print("✓ All jobs stopped")
    print("=" * 80 + "\n")

# Register cleanup handlers
def signal_handler(sig, frame):
    """Handle Ctrl+C and other termination signals"""
    cleanup_all_jobs()
    save_metrics()
    print("Goodbye!")
    os._exit(0)

# Only register handlers in main process (not in Flask reloader)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    # This is the reloader process, don't register handlers
    pass
else:
    # This is the main process or we're not in debug mode
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
    atexit.register(cleanup_all_jobs)

# Initialize on startup
load_metrics()



def recover_stuck_jobs():
    """
    On startup: clean up jobs left in running/pending state from a previous
    server session.

    Rules
    ─────
    • Thread-based jobs (no worker_task_id, or very old heartbeat):
      Mark failed after 2 minutes of silence — worker thread is gone.

    • Celery jobs with worker_task_id set (Celery accepted the task):
      Give a 10-minute grace period.  The task may legitimately sit in
      'pending' waiting for a worker to pick it up, or in 'running' while
      the worker is between heartbeat ticks.  Killing these immediately
      was the source of "worker task is lost → running" flip-flop.

    • Celery jobs with NO worker_task_id:
      The task was never accepted (broker down, submit failed).
      Mark failed immediately so the UI doesn't show a zombie.
    """
    _THREAD_STALE_SECS  = 120    # 2 min for thread jobs
    _CELERY_GRACE_SECS  = 600    # 10 min for Celery jobs

    try:
        with app.app_context():
            stuck = Job.query.filter(Job.status.in_(['running', 'pending'])).all()
            recovered = 0

            for job in stuck:
                now = datetime.utcnow()

                has_celery_task = bool(job.worker_task_id)

                if job.last_heartbeat_at:
                    age = (now - job.last_heartbeat_at).total_seconds()
                else:
                    # No heartbeat ever set — use created_at as proxy
                    age = (now - job.created_at).total_seconds() if job.created_at else 9999

                if has_celery_task:
                    # Celery job — generous grace period
                    stale = age > _CELERY_GRACE_SECS
                    reason = (f"Celery worker lost after {int(age)}s "
                              f"(task {job.worker_task_id[:8]}…)")
                else:
                    # Thread job or task never submitted — short timeout
                    stale = age > _THREAD_STALE_SECS
                    reason = f"Thread worker lost after {int(age)}s (no task ID)"

                if stale:
                    job.status  = 'failed'
                    job.message = f'Interrupted: server restarted while job was running'
                    job.error   = reason
                    recovered  += 1
                    print(f"[Recovery] Marked stuck job {job.id[:8]}… "
                          f"({job.journal}) as failed — {reason}")
                else:
                    print(f"[Recovery] Keeping job {job.id[:8]}… "
                          f"({job.journal}) in '{job.status}' — "
                          f"age={int(age)}s, grace={'Celery' if has_celery_task else 'thread'}")

            # Pre-load stop flags
            stop_jobs = Job.query.filter_by(stop_requested=True).all()
            for j in stop_jobs:
                job_stop_flags[j.id] = True

            db.session.commit()
            print(f"[Recovery] Checked {len(stuck)} stuck jobs "
                  f"({recovered} marked failed), "
                  f"loaded {len(stop_jobs)} stop flags")

    except Exception as e:
        print(f"[Recovery] Error during startup recovery: {e}")

recover_stuck_jobs()

if __name__ == '__main__':
    print("=" * 80)
    print("Journal Scraper Web Server - Enhanced Edition")
    print("=" * 80)
    print("\nFeatures:")
    print("  [+] Multi-journal scraping")
    print("  [+] Real-time dashboard with metrics")
    print("  [+] Job tracking and history")
    print("  [+] Per-journal statistics")
    print("\nAccess Points:")
    print("  * Main Interface: http://localhost:5000")
    print("  * Dashboard:      http://localhost:5000/dashboard")
    print("  * Jobs Manager:   http://localhost:5000/jobs")
    print("\nEnabled Journals:")
    for key, journal in JOURNALS.items():
        if journal['enabled']:
            print(f"  - {journal['name']}")
    print("\n" + "=" * 80 + "\n")
    print("Press Ctrl+C to stop the server and all running scrapers\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)