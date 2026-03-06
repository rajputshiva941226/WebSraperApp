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
from models import db, init_db, Job
from auth_routes import auth_bp
from credit_routes import credit_bp
from master_db_routes import master_db_bp
from admin_routes import admin_bp
from flask_login import LoginManager


app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'results'
app.config['DATA_FOLDER'] = 'data'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///journal_scraper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

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

def _update_job_in_db(job_id, updates):
    """Helper to persist job updates to database"""
    try:
        with app.app_context():
            db_job = Job.query.get(job_id)
            if db_job:
                for key, val in updates.items():
                    if hasattr(db_job, key):
                        if key in ('start_time', 'end_time') and isinstance(val, str):
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


def run_scraper_task(job_id, journal, keyword, start_date, end_date, conference_name='default', mesh_type='all', delay=0):
    """Background task to run the scraper with progress tracking"""
    
    # Apply delay if specified (for staggered selenium scraper starts)
    if delay > 0:
        active_jobs[job_id]['message'] = f'Waiting {delay:.1f}s before starting...'
        time.sleep(delay)
    
    start_time = time.time()
    
    def progress_callback(progress, status, current_url='', links_count=0, authors_count=0, emails_count=0):
        """Callback to update job progress with stats"""
        if job_stop_flags.get(job_id, False):
            raise KeyboardInterrupt("Job stopped by user")
        
        active_jobs[job_id]['progress'] = progress
        active_jobs[job_id]['message'] = status
        active_jobs[job_id]['current_url'] = current_url
        active_jobs[job_id]['links_count'] = links_count
        active_jobs[job_id]['authors_count'] = authors_count
        active_jobs[job_id]['emails_count'] = emails_count
        print(f"[{job_id}] {progress}% - {status} (URL: {current_url}, Links: {links_count}, Authors: {authors_count}, Emails: {emails_count})")
    
    try:
        active_jobs[job_id]['status'] = 'running'
        active_jobs[job_id]['start_time'] = datetime.now().isoformat()
        active_jobs[job_id]['progress'] = 0
        _update_job_in_db(job_id, {'status': 'running', 'start_time': datetime.now().isoformat(), 'progress': 0})
        
        # Use the unified scraper adapter
        from scraper_adapter import ScraperAdapter
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Get driver path
        driver_path = ChromeDriverManager().install()
        
        # Initialize adapter with progress callback
        adapter = ScraperAdapter(job_id=job_id, output_dir=app.config['UPLOAD_FOLDER'])
        adapter.set_progress_callback(progress_callback)
        
        # Run the scraper with conference name and mesh type
        output_file, summary = adapter.run_scraper(
            scraper_type=journal,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            driver_path=driver_path,
            conference_name=conference_name,
            mesh_type=mesh_type
        )
        
        # Count results with unique counts
        authors_count, emails_count, unique_authors, unique_emails, unique_links = count_results_detailed(output_file)
        
        duration = time.time() - start_time
        
        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['end_time'] = datetime.now().isoformat()
        active_jobs[job_id]['duration'] = duration
        active_jobs[job_id]['output_file'] = output_file
        active_jobs[job_id]['authors_count'] = authors_count
        active_jobs[job_id]['emails_count'] = emails_count
        active_jobs[job_id]['unique_authors'] = unique_authors
        active_jobs[job_id]['unique_emails'] = unique_emails
        active_jobs[job_id]['unique_links'] = unique_links
        active_jobs[job_id]['progress'] = 100
        active_jobs[job_id]['message'] = f'✓ Completed! Found {unique_authors} unique authors, {unique_emails} unique emails'
        _update_job_in_db(job_id, {
            'status': 'completed', 'end_time': datetime.now().isoformat(),
            'duration': duration, 'output_file': output_file,
            'authors_count': authors_count, 'emails_count': emails_count,
            'unique_authors': unique_authors, 'unique_emails': unique_emails,
            'unique_links': unique_links, 'progress': 100,
            'message': f'✓ Completed! Found {unique_authors} unique authors, {unique_emails} unique emails'
        })
        
        # Update metrics
        update_journal_metrics(journal, active_jobs[job_id])
        
        # Add to history
        job_history.append(dict(active_jobs[job_id]))
        save_metrics()
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Check for partial results even on failure
        partial_output_file = None
        partial_stats = {'authors': 0, 'emails': 0, 'unique_authors': 0, 'unique_emails': 0, 'unique_links': 0}
        
        # Try to find any CSV files that may have been created
        try:
            # Check in results directory
            results_dir = app.config['UPLOAD_FOLDER']
            possible_files = [
                os.path.join(results_dir, f"{job_id}_{journal}_results.csv"),
                os.path.join(results_dir, f"{job_id}_{JOURNALS[journal]['name'].replace(' ', '_')}_results.csv")
            ]
            
            # Also check keyword-based directories that scrapers might create
            keyword_dir = keyword.replace(' ', '-')
            if os.path.exists(keyword_dir):
                import glob
                keyword_files = glob.glob(os.path.join(keyword_dir, f"*{journal}*.csv"))
                possible_files.extend(keyword_files)
            
            # Find the first existing file
            for pf in possible_files:
                if pf and os.path.exists(pf):
                    partial_output_file = pf
                    break
            
            # If we found a partial file, calculate stats
            if partial_output_file:
                authors_count, emails_count, unique_authors, unique_emails, unique_links = count_results_detailed(partial_output_file)
                partial_stats = {
                    'authors': authors_count,
                    'emails': emails_count,
                    'unique_authors': unique_authors,
                    'unique_emails': unique_emails,
                    'unique_links': unique_links
                }
                print(f"[{job_id}] Found partial results: {unique_authors} authors, {unique_emails} emails, {unique_links} links")
        except Exception as partial_error:
            print(f"[{job_id}] Error checking for partial results: {partial_error}")
        
        # Update job status with error and partial results
        active_jobs[job_id]['status'] = 'failed'
        active_jobs[job_id]['end_time'] = datetime.now().isoformat()
        active_jobs[job_id]['duration'] = duration
        active_jobs[job_id]['error'] = str(e)
        active_jobs[job_id]['progress'] = 0
        
        # If we have partial results, include them
        if partial_output_file and partial_stats['unique_emails'] > 0:
            active_jobs[job_id]['output_file'] = partial_output_file
            active_jobs[job_id]['authors_count'] = partial_stats['authors']
            active_jobs[job_id]['emails_count'] = partial_stats['emails']
            active_jobs[job_id]['unique_authors'] = partial_stats['unique_authors']
            active_jobs[job_id]['unique_emails'] = partial_stats['unique_emails']
            active_jobs[job_id]['unique_links'] = partial_stats['unique_links']
            active_jobs[job_id]['has_partial_results'] = True
            active_jobs[job_id]['message'] = f'⚠️ Failed with partial results: {str(e)[:100]}... | Found {partial_stats["unique_emails"]} emails, {partial_stats["unique_authors"]} authors'
        else:
            active_jobs[job_id]['message'] = f'✗ Failed: {str(e)}'
            active_jobs[job_id]['has_partial_results'] = False
        _update_job_in_db(job_id, {
            'status': active_jobs[job_id]['status'],
            'end_time': active_jobs[job_id]['end_time'],
            'duration': duration, 'error': str(e), 'progress': 0,
            'output_file': active_jobs[job_id].get('output_file'),
            'authors_count': active_jobs[job_id].get('authors_count', 0),
            'emails_count': active_jobs[job_id].get('emails_count', 0),
            'unique_authors': active_jobs[job_id].get('unique_authors', 0),
            'unique_emails': active_jobs[job_id].get('unique_emails', 0),
            'unique_links': active_jobs[job_id].get('unique_links', 0),
            'has_partial_results': active_jobs[job_id].get('has_partial_results', False),
            'message': active_jobs[job_id]['message']
        })
        
        # Update metrics
        update_journal_metrics(journal, active_jobs[job_id])
        
        # Add to history
        job_history.append(dict(active_jobs[job_id]))
        save_metrics()

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
                
                # Extract author name (try different column names)
                author = row.get('Author_Name') or row.get('Name') or row.get('author_name') or ''
                if author and author.strip() and author.strip() != 'N/A':
                    unique_authors.add(author.strip().lower())
                
                # Extract email
                email = row.get('Email') or row.get('email') or ''
                if email and '@' in email and email.strip() != 'N/A':
                    unique_emails.add(email.strip().lower())
                
                # Extract link/URL
                link = row.get('Article_URL') or row.get('URL') or row.get('Article URL') or ''
                if link and link.strip() and link.strip() != 'N/A':
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
    """API endpoint to start scraping jobs (supports multiple journals)"""
    try:
        data = request.get_json()
        
        # Support both single journal (backward compatibility) and multiple journals
        journals = data.get('journals', [])
        if not journals and 'journal' in data:
            journals = [data['journal']]
        
        if not journals:
            return jsonify({'error': 'No journals selected'}), 400
        
        # Validate all journals
        for journal in journals:
            if journal not in JOURNALS or not JOURNALS[journal]['enabled']:
                return jsonify({'error': f'Invalid or disabled journal: {journal}'}), 400
        
        # Get conference name and mesh type
        conference_name = data.get('conference_name', 'default')
        mesh_type = data.get('mesh_type', 'all')
        
        # Create job entries for each journal
        job_ids = []
        selenium_count = 0  # Track selenium scrapers for delay
        user_id = session.get('user_id')
        
        for idx, journal in enumerate(journals):
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            job_ids.append(job_id)
            
            # Create job entry in memory
            active_jobs[job_id] = {
                'id': job_id,
                'user_id': user_id,
                'journal': journal,
                'journal_name': JOURNALS[journal]['name'],
                'keyword': data['keyword'],
                'conference': conference_name,
                'conference_name': conference_name,
                'mesh_type': mesh_type if journal == 'pubmed' else None,
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'authors_count': 0,
                'emails_count': 0,
                'links_count': 0,
                'unique_authors': 0,
                'unique_emails': 0,
                'unique_links': 0,
                'current_url': '',
                'progress': 0,
                'message': 'Job queued',
                'paused': False
            }
            
            # Persist job to database
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
                    created_at=datetime.utcnow()
                )
                db.session.add(db_job)
                db.session.commit()
            except Exception as db_err:
                print(f"[DB] Failed to save job to DB: {db_err}")
                db.session.rollback()
            
            # Initialize stop flag
            job_stop_flags[job_id] = False
            
            # Add delay between selenium-based scrapers (3-5 seconds)
            # API-based scrapers (europepmc, pubmed) can start immediately
            delay = 0
            if JOURNALS[journal]['type'] == 'selenium':
                if selenium_count > 0:
                    import random
                    delay = random.uniform(3, 5)
                selenium_count += 1
            
            # Start scraping in background thread with delay
            thread = threading.Thread(
                target=run_scraper_task,
                args=(job_id, journal, data['keyword'], data['start_date'], data['end_date'], 
                      conference_name, mesh_type, delay)
            )
            thread.daemon = True
            thread.start()
            
            # Store thread reference for control
            job_threads[job_id] = thread
            
            # Apply delay here in the main thread to stagger starts
            if delay > 0:
                time.sleep(delay)
        
        return jsonify({
            'success': True,
            'job_ids': job_ids,
            'message': f'Started {len(job_ids)} scraping job(s) successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs')
def list_jobs():
    """List jobs - admins see all, regular users see only their own"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session.get('user_id')
    user_type = session.get('user_type', 'external')
    is_admin = (user_type == 'admin')

    # Fetch from DB (filtered)
    try:
        if is_admin:
            db_jobs = Job.query.order_by(Job.created_at.desc()).limit(200).all()
        else:
            db_jobs = Job.query.filter_by(user_id=user_id).order_by(Job.created_at.desc()).limit(200).all()
        db_job_dicts = {j.id: j.to_dict() for j in db_jobs}
    except Exception as e:
        print(f"[DB] Error fetching jobs: {e}")
        db_job_dicts = {}

    # Merge with in-memory for live progress, respecting user filter
    merged = dict(db_job_dicts)
    for job_id_key, job in active_jobs.items():
        if is_admin or job.get('user_id') == user_id:
            merged[job_id_key] = job

    result = sorted(merged.values(), key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify(result[:200])


@app.route('/api/job-progress/<job_id>')
def job_progress(job_id):
    """Get progress of a running job"""
    if job_id not in active_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = active_jobs[job_id]
    return jsonify({
        'id': job_id,
        'status': job.get('status'),
        'progress': job.get('progress', 0),
        'message': job.get('message', ''),
        'authors_count': job.get('authors_count', 0),
        'emails_count': job.get('emails_count', 0)
    })

@app.route('/api/job-status/<job_id>')
def job_status(job_id):
    """Get the status of a scraping job"""
    if job_id in active_jobs:
        return jsonify(active_jobs[job_id])
    # Check history
    for job in job_history:
        if job.get('id') == job_id:
            return jsonify(job)
    # Check database
    try:
        db_job = Job.query.get(job_id)
        if db_job:
            return jsonify(db_job.to_dict())
    except Exception:
        pass
    return jsonify({'error': 'Job not found'}), 404


@app.route('/api/stop-job/<job_id>', methods=['POST'])
def stop_job(job_id):
    """Stop a running job"""
    # Check active_jobs first
    if job_id in active_jobs:
        job = active_jobs[job_id]
        if job['status'] not in ['running', 'pending']:
            return jsonify({'error': 'Can only stop running or pending jobs'}), 400
        job_stop_flags[job_id] = True
        job['status'] = 'stopped'
        job['end_time'] = datetime.now().isoformat()
        job['message'] = 'Job stopped by user'
        job_history.append(dict(active_jobs[job_id]))
        save_metrics()
        _update_job_in_db(job_id, {'status': 'stopped', 'end_time': datetime.now().isoformat(), 'message': 'Job stopped by user'})
        return jsonify({'success': True, 'message': f'Job {job_id} stopped successfully'})

    # Not in memory - check DB
    try:
        db_job = Job.query.get(job_id)
        if db_job:
            if db_job.status not in ['running', 'pending']:
                return jsonify({'error': f'Job already {db_job.status}'}), 400
            db_job.status = 'stopped'
            db_job.end_time = datetime.utcnow()
            db_job.message = 'Job stopped by user'
            db.session.commit()
            job_stop_flags[job_id] = True
            return jsonify({'success': True, 'message': f'Job {job_id} stopped successfully'})
    except Exception as e:
        print(f"[DB] Error stopping job: {e}")

    return jsonify({'error': 'Job not found'}), 404

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
    
    job = active_jobs.get(job_id)
    
    # If not in active jobs, check history
    if not job:
        for hist_job in job_history:
            if hist_job.get('id') == job_id:
                job = hist_job
                break
    
    # If still not found, check database
    if not job:
        try:
            db_job = Job.query.get(job_id)
            if db_job:
                job = db_job.to_dict()
        except Exception:
            pass
    
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
    
    # Try to find the file in multiple locations
    if not output_file or not os.path.exists(output_file):
        # Try to find in results directory
        results_dir = app.config.get('UPLOAD_FOLDER', 'results')
        possible_files = [
            output_file,
            os.path.join(results_dir, os.path.basename(output_file)) if output_file else None,
            os.path.join(results_dir, f"{job_id}_{job['journal_name']}_results.csv"),
        ]
        
        # Also check keyword-based directories
        keyword_dir = job.get('keyword', '').replace(' ', '-')
        if keyword_dir:
            possible_files.append(os.path.join(keyword_dir, f"{job['journal_name']}_{keyword_dir}*.csv"))
        
        output_file = None
        for pf in possible_files:
            if pf and os.path.exists(pf):
                output_file = pf
                break
            # Try glob pattern
            if pf and '*' in pf:
                import glob
                matches = glob.glob(pf)
                if matches:
                    output_file = matches[0]
                    break
        
        if not output_file:
            return jsonify({'error': f'Output file not found. Searched locations: {[p for p in possible_files if p]}'}), 404
    
    # If XLSX requested, generate it on-the-fly
    if format_type == 'xlsx':
        try:
            # Read CSV
            df = pd.read_csv(output_file)
            
            # Create XLSX with stats sheet
            xlsx_path = output_file.replace('.csv', '.xlsx')
            
            with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
                # Write main results
                df.to_excel(writer, sheet_name='Results', index=False)
                
                # Create stats sheet
                stats_data = {
                    'Metric': [
                        'Total Records',
                        'Unique Emails',
                        'Unique Authors',
                        'Unique URLs',
                        'Scraper',
                        'Keyword',
                        'Date Range',
                        'Completed At'
                    ],
                    'Value': [
                        len(df),
                        df['emails'].nunique() if 'emails' in df.columns else 'N/A',
                        df['Names'].nunique() if 'Names' in df.columns else df['Author'].nunique() if 'Author' in df.columns else 'N/A',
                        df['URL'].nunique() if 'URL' in df.columns else 'N/A',
                        job.get('journal_name', 'Unknown'),
                        job.get('keyword', 'Unknown'),
                        f"{job.get('start_date', 'N/A')} to {job.get('end_date', 'N/A')}",
                        job.get('end_time', 'N/A')
                    ]
                }
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, sheet_name='Statistics', index=False)
            
            return send_file(
                xlsx_path,
                as_attachment=True,
                download_name=f"{job['journal_name']}_{job['keyword'].replace(' ', '_')}_results.xlsx"
            )
        except Exception as e:
            return jsonify({'error': f'Failed to generate XLSX: {str(e)}'}), 500
    
    # Return CSV
    return send_file(
        output_file,
        as_attachment=True,
        download_name=f"{job['journal_name']}_{job['keyword'].replace(' ', '_')}_results.csv"
    )

@app.route('/api/download-bulk')
def download_bulk_results():
    """Download all completed job results as a zip file"""
    import zipfile
    import io

    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    current_user_id = session.get('user_id')
    is_admin = session.get('user_type') == 'admin'
    
    # Get all completed jobs from active jobs and history
    completed_jobs = []
    
    # Check active jobs
    for job in active_jobs.values():
        if job['status'] == 'completed' and job.get('output_file') and (is_admin or job.get('user_id') == current_user_id):
            completed_jobs.append(job)
    
    # Check history
    for job in job_history:
        if job['status'] == 'completed' and job.get('output_file') and (is_admin or job.get('user_id') == current_user_id):
            # Avoid duplicates
            if not any(j['id'] == job['id'] for j in completed_jobs):
                completed_jobs.append(job)

    try:
        db_completed_query = Job.query.filter_by(status='completed') if is_admin else Job.query.filter_by(status='completed', user_id=current_user_id)
        db_completed_jobs = db_completed_query.order_by(Job.created_at.desc()).limit(500).all()
        for db_job in db_completed_jobs:
            job = db_job.to_dict()
            if not any(j['id'] == job['id'] for j in completed_jobs):
                completed_jobs.append(job)
    except Exception as e:
        print(f"[DB] Error fetching completed jobs for bulk download: {e}")
    
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
    active_count = len([j for j in active_jobs.values() if j['status'] in ['pending', 'running']])
    return jsonify({
        'status': 'healthy',
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
