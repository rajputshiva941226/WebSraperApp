"""
Celery Worker — Production-grade task queue for journal scraper jobs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CRITICAL: billiard patch MUST come before ALL other imports.
  undetected_chromedriver uses multiprocessing.Process internally
  for its Chrome patcher. Celery workers run as daemonic processes,
  and Python forbids daemonic processes from spawning children.
  billiard is Celery's own multiprocessing fork that lifts this
  restriction — patching sys.modules here makes uc.Chrome() work
  transparently inside any Celery task.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── PATCH: Must be the absolute first executable lines ──────────
import sys as _sys
import billiard as _billiard
import billiard.process as _billiard_process
import billiard.context as _billiard_context
import billiard.pool as _billiard_pool
from celery.schedules import crontab
_sys.modules['multiprocessing']         = _billiard
_sys.modules['multiprocessing.process'] = _billiard_process
_sys.modules['multiprocessing.context'] = _billiard_context
_sys.modules['multiprocessing.pool']    = _billiard_pool
# ── END PATCH ───────────────────────────────────────────────────

import os
import threading
import time
import glob
import signal
import logging
import subprocess
from datetime import datetime
from celery import Celery
from celery.utils.log import get_task_logger
from celery.exceptions import SoftTimeLimitExceeded
from kombu import Exchange, Queue as KombuQueue

logger = get_task_logger(__name__)

# ── Redis / broker config ────────────────────────────────────────
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Separate broker and result-backend DBs to avoid key collisions
# at scale you can point these at different Redis instances entirely
BROKER_URL  = os.environ.get('CELERY_BROKER_URL',  REDIS_URL)
BACKEND_URL = os.environ.get('CELERY_BACKEND_URL', REDIS_URL.replace('/0', '/1'))

# ── Celery app ───────────────────────────────────────────────────
celery_app = Celery(
    'journal_scraper',
    broker=BROKER_URL,
    backend=BACKEND_URL,
)

# ── Task routing: selenium scrapers get their own dedicated queue ─
#    API scrapers (fast, cheap) share a lightweight queue.
#    This lets you scale selenium workers independently:
#      celery -A celery_worker worker -Q selenium --concurrency=2
#      celery -A celery_worker worker -Q api      --concurrency=8
SELENIUM_SCRAPERS = {
    'springer', 'cambridge', 'bmj', 'nature',
    'oxford', 'lippincott', 'sage', 'emerald', 'mdpi',
    'tandf', 'wiley', 'sciencedirect',
}
API_SCRAPERS = {'europepmc', 'pubmed'}
DOCUMENT_SCRAPERS = {'pdf_scraper', 'pdf_scraper_phase2'}  # No Chrome — runs in-process

_selenium_exchange = Exchange('selenium', type='direct')
_api_exchange       = Exchange('api',      type='direct')
_default_exchange   = Exchange('default',  type='direct')

celery_app.conf.update(
    # ── Serialisation ──────────────────────────────────────────
    task_serializer   = 'json',
    result_serializer = 'json',
    accept_content    = ['json'],

    # ── Timezone ───────────────────────────────────────────────
    timezone   = 'UTC',
    enable_utc = True,

    # ── Reliability ────────────────────────────────────────────
    task_track_started       = True,
    task_acks_late           = True,   # Re-queue if worker crashes mid-task
    task_reject_on_worker_lost = True, # Explicit reject so broker re-queues
    worker_prefetch_multiplier = 1,    # One task per worker (scrapers are heavy)

    # ── Time limits ────────────────────────────────────────────
    # Springer scraping 1000+ articles at ~5s each = 5000+ seconds.
    # 8 h soft limit gives even the largest Springer/Cambridge jobs room.
    # Hard kill is 30 min after soft so cleanup code has time to run.
    task_soft_time_limit = 86_400,  # 8 h  → raises SoftTimeLimitExceeded
    task_time_limit      = 86_400 + 1800 ,  # 8.5 h → hard SIGKILL

    # ── Result expiry ──────────────────────────────────────────
    result_expires = 172_800,        # Keep results in Redis for 2 days

    # ── Queues & routing ───────────────────────────────────────
    task_queues = (
        KombuQueue('selenium', _selenium_exchange, routing_key='selenium'),
        KombuQueue('api',      _api_exchange,      routing_key='api'),
        KombuQueue('default',  _default_exchange,  routing_key='default'),
    ),
    task_default_queue       = 'default',
    task_default_exchange    = 'default',
    task_default_routing_key = 'default',

    # Route tasks automatically by journal type (set in apply_async kwargs)
    task_routes = {
        'celery_worker.run_scraper_task': {
            # Dynamic routing is handled inside apply_async via `queue=` kwarg
            # (see app.py start_scraping() — pass queue='selenium' or 'api')
        },
    },

    # ── Worker behaviour ───────────────────────────────────────
    worker_max_tasks_per_child = 10,   # Recycle worker after 10 tasks → prevents Chrome memory leaks
    worker_max_memory_per_child = 512_000,  # 512 MB hard limit per child process

    # ── Broker connection resilience ───────────────────────────
    broker_connection_retry_on_startup = True,
    broker_connection_max_retries      = 10,
    broker_transport_options = {
        'visibility_timeout': 32_400,  # 9 h — must be > task_time_limit
        'max_retries': 5,
    },
            # ── Celery Beat periodic tasks ────────────────────────────
    beat_schedule = {
            # Daily master-DB sync: runs every day at 00:30 UTC.
            # Processes all jobs completed in the previous 24 h.
            'sync-master-db-daily': {
                'task':     'celery_worker.sync_master_database_daily',
                'schedule': crontab(hour=0, minute=30),
                'kwargs':   {'days_back': 1},
            },
        },
    beat_scheduler = 'celery.beat:PersistentScheduler',  # stores beat state on disk
    redis_max_connections = 20,
    
    
    )
    # ── Result backend ─────────────────────────────────────────



# ── Helpers ──────────────────────────────────────────────────────

def _get_flask_app():
    """Import Flask app lazily to avoid circular imports."""
    from app import app
    return app


def _db_update(job_id: str, updates: dict) -> None:
    """
    Update a Job row safely from a Celery worker process.
    Uses its own app context so it never touches Flask's request context.
    """
    flask_app = _get_flask_app()
    try:
        with flask_app.app_context():
            from models import db, Job
            db_job = Job.query.get(job_id)
            if not db_job:
                return
            for key, val in updates.items():
                if not hasattr(db_job, key):
                    continue
                if key in ('start_time', 'end_time', 'last_heartbeat_at') and isinstance(val, str):
                    try:
                        setattr(db_job, key, datetime.fromisoformat(val))
                    except (ValueError, TypeError):
                        pass
                else:
                    setattr(db_job, key, val)
            db.session.commit()
    except Exception as exc:
        logger.warning("[DB] Failed to update job %s: %s", job_id[:8], exc)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def _is_stop_requested(job_id: str) -> bool:
    """
    Poll DB for cooperative stop flag.
    Called periodically from the progress callback — cheap single-row query.
    """
    flask_app = _get_flask_app()
    try:
        with flask_app.app_context():
            from models import Job
            db_job = Job.query.get(job_id)
            return bool(db_job and db_job.stop_requested)
    except Exception:
        return False


def _count_results_detailed(filepath: str):
    """
    Count unique authors, emails, links in a CSV output file.
    Returns (total_rows, emails_count, unique_authors, unique_emails, unique_links).
    """
    if not filepath or not os.path.exists(filepath):
        return 0, 0, 0, 0, 0
    try:
        import csv
        unique_authors = set()
        unique_emails  = set()
        unique_links   = set()
        total_rows     = 0

        with open(filepath, 'r', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                total_rows += 1

                author = (row.get('Author_Name') or row.get('author_name') or
                          row.get('full_name')   or row.get('Name') or
                          row.get('name')         or row.get('first_name') or '')
                if author and author.strip() and author.strip().lower() != 'n/a':
                    unique_authors.add(author.strip().lower())

                email = (row.get('Email')         or row.get('email') or
                         row.get('Email_Address') or row.get('email_address') or '')
                if email and '@' in email and email.strip().lower() != 'n/a':
                    unique_emails.add(email.strip().lower())

                link = (row.get('Article_URL') or row.get('article_url') or
                        row.get('URL')         or row.get('url') or
                        row.get('pub_url')     or row.get('link') or
                        row.get('doi')         or row.get('DOI') or '')
                if link and link.strip() and link.strip().lower() != 'n/a':
                    unique_links.add(link.strip())

        return total_rows, len(unique_emails), len(unique_authors), len(unique_emails), len(unique_links)

    except Exception as exc:
        logger.warning("[CountResults] Error: %s", exc)
        return 0, 0, 0, 0, 0


def _find_partial_csv(job_output_dir: str) -> str | None:
    """
    Return the best partial-results CSV in the job output directory.
    Prefers author/email files over Phase-1 URL-collection files.
    Springer (and Cambridge) both write two CSVs:
      *_urls.csv     → article links only  (Phase 1 — never the download target)
      *_authors.csv  → emails + authors    (Phase 2 — this is what users want)
    """
    try:
        all_files = glob.glob(os.path.join(job_output_dir, '*.csv'))
        if not all_files:
            return None

        # Priority 1: files with 'author' or 'email' in name (exclude url-only)
        email_files = [
            f for f in all_files
            if any(k in os.path.basename(f).lower() for k in ('author', 'email', 'result'))
            and '_urls' not in os.path.basename(f).lower()
        ]
        if email_files:
            return email_files[0]

        # Priority 2: any file that isn't a pure url-collection file
        non_url_files = [
            f for f in all_files
            if '_urls' not in os.path.basename(f).lower()
        ]
        if non_url_files:
            return non_url_files[0]

        # Last resort: return whatever exists (even if it's a urls file)
        return all_files[0]

    except Exception:
        return None


# ── Chrome process cleanup ───────────────────────────────────────

def _kill_orphaned_chrome(worker_pid: int | None = None) -> None:
    """
    Kill Chrome / chromedriver processes that are children of this worker.

    Called in the task's finally block so every code path (success,
    failure, timeout, user-stop) cleans up Chrome.

    Strategy:
      1. If we know the worker PID, kill only its direct Chrome children
         (safe — won't touch Chrome opened by other concurrent workers).
      2. Fallback: kill any chrome/chromedriver with no living parent
         (zombie / orphaned).
    """
    try:
        my_pid = worker_pid or os.getpid()

        # Find child PIDs of this worker that are chrome or chromedriver
        try:
            result = subprocess.run(
                ['ps', '--ppid', str(my_pid), '-o', 'pid,comm', '--no-headers'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    pid_str, comm = parts
                    if 'chrome' in comm.lower():
                        try:
                            os.kill(int(pid_str), signal.SIGKILL)
                            logger.info("[ChromeCleanup] Killed child chrome PID %s", pid_str)
                        except (ProcessLookupError, ValueError):
                            pass
        except Exception as e:
            logger.debug("[ChromeCleanup] ps child scan failed: %s", e)

        # Also kill any chromedriver processes owned by this user that are
        # no longer attached to a live parent (ppid=1 means reparented to init)
        try:
            result = subprocess.run(
                ['pgrep', '-u', str(os.getuid()), '-x', 'chromedriver'],
                capture_output=True, text=True, timeout=5
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str)
                    # Check parent PID
                    with open(f'/proc/{pid}/status') as f:
                        for line in f:
                            if line.startswith('PPid:'):
                                ppid = int(line.split()[1])
                                if ppid == 1:  # reparented to init → orphan
                                    os.kill(pid, signal.SIGKILL)
                                    logger.info("[ChromeCleanup] Killed orphaned chromedriver PID %s", pid)
                                break
                except (ProcessLookupError, ValueError, FileNotFoundError):
                    pass
        except Exception as e:
            logger.debug("[ChromeCleanup] chromedriver orphan scan failed: %s", e)

    except Exception as exc:
        logger.warning("[ChromeCleanup] Cleanup failed: %s", exc)


# ── Main Celery task ─────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name='celery_worker.run_scraper_task',

    # ── Auto-retry on transient infra errors (not scraper logic errors) ──
    # Raised by SoftTimeLimitExceeded, Redis blips, etc.
    autoretry_for=(OSError, ConnectionError),
    max_retries=2,
    retry_backoff=30,       # 30 s, 60 s
    retry_backoff_max=120,

    # ── Per-task time limits (match global config above) ────────────
    soft_time_limit=28_800,   # 8 h
    time_limit=30_600,        # 8.5 h
)
def run_scraper_task(
    self,
    job_id:          str,
    user_id:         str,
    journal:         str,
    keyword:         str,
    start_date:      str,
    end_date:        str,
    conference_name: str = 'default',
    mesh_type:       str = 'all',
):
    """
    Execute a single scraper job inside a Celery worker.

    Routing hint for callers (app.py):
        queue = 'selenium' if journal in SELENIUM_SCRAPERS else 'api'
        run_scraper_task.apply_async(..., queue=queue)

    Worker startup examples:
        # 2 selenium workers (Chrome-heavy)
        celery -A celery_worker worker -Q selenium --concurrency=2 -n selenium@%h

        # 8 API workers (lightweight)
        celery -A celery_worker worker -Q api --concurrency=8 -n api@%h

        # All-in-one (dev / small EC2)
        celery -A celery_worker worker -Q selenium,api,default --concurrency=4
    """
    flask_app = _get_flask_app()

    # Per-job isolated output directory
    upload_folder  = flask_app.config.get('UPLOAD_FOLDER', 'results')
    job_output_dir = os.path.join(upload_folder, user_id, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    # Ensure directory is accessible by Flask process (different user on EC2)
    for path in [upload_folder, os.path.join(upload_folder, user_id), job_output_dir]:
        try:
            os.chmod(path, 0o777)
        except OSError:
            pass

    start_time = time.monotonic()

    # ── Heartbeat thread ────────────────────────────────────────
    # Updates DB every 15 s so stuck-job detection and monitoring dashboards
    # can tell a worker is still alive without polling task state.
    _heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        while not _heartbeat_stop.is_set():
            _db_update(job_id, {'last_heartbeat_at': datetime.utcnow().isoformat()})
            _heartbeat_stop.wait(15)

    heartbeat = threading.Thread(target=_heartbeat_loop, daemon=True, name=f'heartbeat-{job_id[:8]}')
    heartbeat.start()

    # ── Progress callback ───────────────────────────────────────
    # Passed into ScraperAdapter so scrapers can report live progress.
    # Also polls for cooperative stop.
    _last_stop_check = [0.0]

    def progress_callback(
        progress:      int,
        status:        str,
        current_url:   str = '',
        links_count:   int = 0,
        authors_count: int = 0,
        emails_count:  int = 0,
    ):
        now = time.monotonic()
        # Cooperative stop — check at most every 2 s to avoid DB hammering
        if now - _last_stop_check[0] > 2:
            _last_stop_check[0] = now
            if _is_stop_requested(job_id):
                raise KeyboardInterrupt('Job stopped by user')

        # Persist every 5 progress points to avoid DB write storm
        if progress % 5 == 0 or progress == 100:
            _db_update(job_id, {
                'progress':            progress,
                'message':             status,
                'current_url':         current_url,
                'links_count':         links_count,
                'authors_count':       authors_count,
                'emails_count':        emails_count,
                'last_heartbeat_at':   datetime.utcnow().isoformat(),
            })
        logger.info("[%s][%s] %d%% — %s", journal.upper(), job_id[:8], progress, status)

    # ── Execution ───────────────────────────────────────────────
    try:
        _db_update(job_id, {
            'status':         'running',
            'start_time':     datetime.utcnow().isoformat(),
            'progress':       0,
            'worker_task_id': self.request.id or job_id,
        })

        from scraper_adapter import ScraperAdapter

        # Only install ChromeDriver for Selenium scrapers.
        # API and document scrapers never touch Chrome.
        driver_path = None
        if journal in SELENIUM_SCRAPERS and journal not in DOCUMENT_SCRAPERS:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            logger.info("[%s] ChromeDriver installed at %s", journal.upper(), driver_path)

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
                mesh_type=mesh_type,
            )

        total_rows, emails_count, unique_authors, unique_emails, unique_links = \
            _count_results_detailed(output_file)
        duration = time.monotonic() - start_time
        msg = f'\u2713 Completed! Found {unique_authors} unique authors, {unique_emails} unique emails'

        _db_update(job_id, {
            'status':        'completed',
            'end_time':      datetime.utcnow().isoformat(),
            'duration':      duration,
            'output_file':   output_file,
            'authors_count': total_rows,
            'emails_count':  emails_count,
            'unique_authors': unique_authors,
            'unique_emails':  unique_emails,
            'unique_links':   unique_links,
            'progress':      100,
            'message':       msg,
        })
        logger.info("[%s][%s] DONE — %s", journal.upper(), job_id[:8], msg)

    except KeyboardInterrupt:
        # Cooperative user-requested stop
        duration = time.monotonic() - start_time
        _db_update(job_id, {
            'status':   'stopped',
            'end_time': datetime.utcnow().isoformat(),
            'duration': duration,
            'message':  'Job stopped by user',
            'progress': 0,
        })
        logger.info("[%s][%s] STOPPED by user", journal.upper(), job_id[:8])

    except SoftTimeLimitExceeded:
        # Task ran past the soft time limit — save partial results if any,
        # then let the finally block kill Chrome before the hard SIGKILL arrives.
        duration = time.monotonic() - start_time
        logger.warning("[%s][%s] SOFT TIME LIMIT exceeded after %.0fs",
                       journal.upper(), job_id[:8], duration)
        partial = _find_partial_csv(job_output_dir)
        if partial:
            pa, pe, pua, pue, pul = _count_results_detailed(partial)
            has_partial = (pue > 0 or pua > 0 or pa > 0)
        else:
            pa = pe = pua = pue = pul = 0
            has_partial = False
        _db_update(job_id, {
            'status':              'failed',
            'end_time':            datetime.utcnow().isoformat(),
            'duration':            duration,
            'error':               'SoftTimeLimitExceeded: job exceeded maximum allowed runtime',
            'progress':            0,
            'output_file':         partial if has_partial else None,
            'authors_count':       pa,
            'emails_count':        pe,
            'unique_authors':      pua,
            'unique_emails':       pue,
            'unique_links':        pul,
            'has_partial_results': has_partial,
            'message': (
                f'\u26a0\ufe0f Time limit exceeded (>{duration/3600:.1f}h). '
                f'Partial: {pue} emails, {pua} authors'
                if has_partial else
                f'\u2717 Failed: exceeded maximum runtime ({duration/3600:.1f}h)'
            ),
        })

    except Exception as exc:
        duration = time.monotonic() - start_time
        logger.exception("[%s][%s] FAILED: %s", journal.upper(), job_id[:8], exc)

        partial = _find_partial_csv(job_output_dir)
        if partial:
            pa, pe, pua, pue, pul = _count_results_detailed(partial)
            has_partial = (pue > 0 or pua > 0 or pa > 0)
            msg = (
                f'\u26a0\ufe0f Failed with partial results: {str(exc)[:100]}... '
                f'| Found {pue} emails, {pua} authors'
            ) if has_partial else f'\u2717 Failed: {exc}'
            _db_update(job_id, {
                'status':             'failed',
                'end_time':           datetime.utcnow().isoformat(),
                'duration':           duration,
                'error':              str(exc),
                'progress':           0,
                'output_file':        partial if has_partial else None,
                'authors_count':      pa,
                'emails_count':       pe,
                'unique_authors':     pua,
                'unique_emails':      pue,
                'unique_links':       pul,
                'has_partial_results': has_partial,
                'message':            msg,
            })
        else:
            _db_update(job_id, {
                'status':              'failed',
                'end_time':            datetime.utcnow().isoformat(),
                'duration':            duration,
                'error':               str(exc),
                'progress':            0,
                'has_partial_results': False,
                'message':             f'\u2717 Failed: {exc}',
            })

    finally:
        _heartbeat_stop.set()
        heartbeat.join(timeout=5)
        # Kill any Chrome/chromedriver processes spawned by this task.
        # Runs on every exit path: success, failure, timeout, user-stop.
        _kill_orphaned_chrome(worker_pid=os.getpid())


# ── Health-check task (optional, useful for monitoring) ──────────

@celery_app.task(name='celery_worker.ping')
def ping():
    """Lightweight task for load-balancer / uptime health checks."""
    return {'status': 'ok', 'ts': datetime.utcnow().isoformat()}

@celery_app.task(
    name='celery_worker.sync_master_database_daily',
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5-minute retry delay
)
def sync_master_database_daily(self, days_back: int = 1, dry_run: bool = False):
    """
    Celery Beat periodic task: sync completed job results → master database.
 
    Runs daily at 00:30 UTC (configured in beat_schedule above).
    Can also be triggered ad-hoc from the admin panel via the
    POST /api/master-database/sync-daily endpoint.
 
    Args:
        days_back: How many days of completed jobs to re-process.
                   Default 1 = only yesterday's jobs.
                   Set to 7 for a weekly full-resync if needed.
        dry_run:   If True, counts changes but does not write to DB.
                   Useful for sanity-checks before production syncs.
    """
    flask_app = _get_flask_app()
 
    logger.info(
        "[MasterDB Sync] Starting daily sync (days_back=%d, dry_run=%s)",
        days_back, dry_run
    )
 
    try:
        with flask_app.app_context():
            from master_db_routes import _run_daily_sync
            result = _run_daily_sync(days_back=days_back, dry_run=dry_run, celery_task=self)
 
        logger.info(
            "[MasterDB Sync] Done — jobs_processed=%d  added=%d  updated=%d  skipped=%d  errors=%d",
            result['jobs_processed'],
            result['records_added'],
            result['records_updated'],
            result['records_skipped'],
            len(result.get('errors', [])),
        )
        if result.get('errors'):
            for err in result['errors']:
                logger.warning("[MasterDB Sync] Job %s error: %s", err['job_id'], err['error'])
 
        return result
 
    except Exception as exc:
        logger.exception("[MasterDB Sync] Failed: %s", exc)
        # Auto-retry up to max_retries times before giving up
        raise self.retry(exc=exc)