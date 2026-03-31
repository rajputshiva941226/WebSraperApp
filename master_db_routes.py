"""
Master Database Routes
──────────────────────
Handles master database operations, conference data upload,
daily auto-sync from completed jobs, and admin downloads.

Changes vs original:
  • download_master_database  — supports conference_code and keyword filters
  • append_scraped_results     — writes conference_code alongside conference_name
  • sync_daily                 — NEW: manual admin trigger for daily sync
  • master_database_stats      — extended with per-conference + per-keyword breakdown
  • conferences_dropdown       — NEW: active conferences for job-submission forms
"""

from flask import Blueprint, request, jsonify, render_template, send_file, session
from models import db, MasterDatabase, ConferenceMaster, User
from auth import admin_required, internal_user_required, get_current_user
from werkzeug.utils import secure_filename
import os
import csv
import uuid
import pandas as pd
from datetime import datetime, timedelta
import io

master_db_bp = Blueprint('master_db', __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/master-database')
@internal_user_required
def master_database_page():
    """Master database management page (internal users only)."""
    return render_template('master_database.html')


# ═══════════════════════════════════════════════════════════════════
# Upload conference master data (CSV / XLSX)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/upload', methods=['POST'])
@internal_user_required
def upload_conference_data():
    """
    Upload conference master data.
    Expects CSV/XLSX with columns: author_name, email, affiliation (optional).
    Also accepts conference_code in the form fields to stamp records.
    """
    user = get_current_user()

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Use CSV or XLSX'}), 400

    conference_name     = request.form.get('conference_name')
    conference_code     = (request.form.get('conference_code') or '').strip().upper()
    conference_year     = request.form.get('conference_year', type=int)
    conference_location = request.form.get('conference_location', '')

    if not conference_name:
        return jsonify({'error': 'Conference name is required'}), 400

    try:
        filename = secure_filename(file.filename)
        df = pd.read_csv(file) if filename.endswith('.csv') else pd.read_excel(file)

        missing = [c for c in ['author_name', 'email'] if c not in df.columns]
        if missing:
            return jsonify({'error': f'Missing required columns: {", ".join(missing)}'}), 400

        added = updated = skipped = 0

        for _, row in df.iterrows():
            email       = str(row['email']).strip().lower()
            author_name = str(row['author_name']).strip()
            affiliation = str(row.get('affiliation', '')).strip() if 'affiliation' in row else ''

            if not email or '@' not in email:
                skipped += 1
                continue

            existing = ConferenceMaster.query.filter_by(
                conference_name=conference_name, email=email
            ).first()

            if existing:
                existing.author_name        = author_name
                existing.affiliation        = affiliation
                existing.conference_year    = conference_year
                existing.conference_location = conference_location
                existing.conference_code    = conference_code
                updated += 1
            else:
                db.session.add(ConferenceMaster(
                    conference_name=conference_name,
                    conference_code=conference_code,
                    conference_year=conference_year,
                    conference_location=conference_location,
                    author_name=author_name,
                    email=email,
                    affiliation=affiliation,
                    uploaded_by=user.id,
                    source_file=filename,
                ))
                added += 1

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Upload complete',
            'records_added': added,
            'records_updated': updated,
            'records_skipped': skipped,
            'total_processed': added + updated + skipped,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500


# ═══════════════════════════════════════════════════════════════════
# Append scraped results → master DB (called after job completes)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/append-scraped', methods=['POST'])
@internal_user_required
def append_scraped_results():
    """
    Auto-append scraped results to master database.
    Deduplicates based on email. Stamps conference_code when available.
    """
    data   = request.json
    job_id = data.get('job_id')

    if not job_id:
        return jsonify({'error': 'Job ID is required'}), 400

    from models import Job as JobModel
    db_job = JobModel.query.get(job_id)
    if not db_job:
        return jsonify({'error': 'Job not found'}), 404
    job = db_job.to_dict()

    output_file = job.get('output_file')
    if not output_file or not os.path.exists(output_file):
        return jsonify({'error': 'Output file not found'}), 404

    # Resolve conference_code from the job's conference_name
    conf_name = job.get('conference', '') or job.get('conference_name', '')
    conf_code = _resolve_conference_code(conf_name)

    try:
        added = updated = skipped = 0

        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                email        = (row.get('Email') or row.get('email') or row.get('emails', '')).strip().lower()
                author_name  = row.get('Author_Name') or row.get('Name') or row.get('author_name') or row.get('Names', '')
                affiliation  = row.get('Affiliation') or row.get('affiliation', '')
                article_url  = row.get('Article_URL') or row.get('URL') or row.get('Article URL', '')
                article_title = row.get('Title') or row.get('title', '')

                # Override conf_code with CSV column if present
                csv_conf_code = (row.get('Conference_Code') or row.get('conference_code', '')).strip().upper()
                effective_code = csv_conf_code or conf_code

                if not email or '@' not in email or email == 'n/a':
                    skipped += 1
                    continue

                existing = MasterDatabase.query.filter_by(email=email).first()
                if existing:
                    existing.author_name   = author_name  or existing.author_name
                    existing.affiliation   = affiliation  or existing.affiliation
                    existing.article_url   = article_url  or existing.article_url
                    existing.article_title = article_title or existing.article_title
                    existing.conference_code = effective_code or existing.conference_code
                    existing.updated_at    = datetime.utcnow()
                    updated += 1
                else:
                    db.session.add(MasterDatabase(
                        author_name=author_name,
                        email=email,
                        affiliation=affiliation,
                        conference_name=conf_name,
                        conference_code=effective_code,
                        journal_name=job.get('journal_name', ''),
                        article_title=article_title,
                        article_url=article_url,
                        keyword=job.get('keyword', ''),
                        job_id=job_id,
                    ))
                    added += 1

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Results appended to master database',
            'records_added': added,
            'records_updated': updated,
            'records_skipped': skipped,
            'total_processed': added + updated + skipped,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to append results: {str(e)}'}), 500


# ═══════════════════════════════════════════════════════════════════
# NEW: Daily sync (manual admin trigger + called by Celery Beat)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/sync-daily', methods=['POST'])
@admin_required
def sync_daily_manual():
    """
    Manual admin trigger for the daily master-DB sync.
    Scans completed jobs from the last N days (default 1) and merges
    unique emails into the master database.

    Body (JSON, all optional):
        days_back  int   — how many days of history to sync (default 1)
        dry_run    bool  — if true, counts only, no DB writes

    This is the same logic used by the Celery Beat scheduled task.
    """
    data     = request.get_json(silent=True) or {}
    days_back = int(data.get('days_back', 1))
    dry_run   = bool(data.get('dry_run', False))

    result = _run_daily_sync(days_back=days_back, dry_run=dry_run)
    return jsonify(result)


# Redis key that tracks the currently active sync task_id
_SYNC_LOCK_KEY = 'masterdb:sync:current_task_id'


def _get_redis():
    import redis as redis_lib
    return redis_lib.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
                              decode_responses=True)


@master_db_bp.route('/api/master-database/sync-all', methods=['POST'])
@admin_required
def sync_all_historical():
    """
    Async trigger to backfill ALL completed jobs into master DB via Celery.
    Returns immediately with a task_id; poll /api/master-database/task-status/<id>.
    Prevents duplicate dispatches — if a sync is already running returns the
    existing task_id instead of queuing a second one.
    """
    from celery_worker import celery_app, sync_master_database_daily

    try:
        r = _get_redis()
        existing_id = r.get(_SYNC_LOCK_KEY)
        if existing_id:
            existing_task = celery_app.AsyncResult(existing_id)
            if existing_task.state in ('PENDING', 'STARTED', 'PROGRESS'):
                return jsonify({
                    'task_id': existing_id,
                    'status':  'already_running',
                    'sync_type': 'full_historical',
                })
            # RETRY / FAILURE / SUCCESS → stale lock; allow fresh dispatch
    except Exception:
        pass  # Redis unavailable — proceed with dispatch

    task = sync_master_database_daily.apply_async(kwargs={'days_back': 36500, 'dry_run': False})

    try:
        r.set(_SYNC_LOCK_KEY, task.id, ex=172800)  # expire after 2 days
    except Exception:
        pass

    return jsonify({'task_id': task.id, 'status': 'started', 'sync_type': 'full_historical'})


@master_db_bp.route('/api/master-database/task-status/<task_id>')
@admin_required
def sync_task_status(task_id):
    """Poll the status of an async sync task."""
    from celery_worker import celery_app
    task = celery_app.AsyncResult(task_id)
    if task.state in ('PENDING', 'STARTED'):
        # PENDING = task is queued but no worker has picked it up yet.
        # STARTED = worker claimed it but update_state hasn't fired yet.
        return jsonify({'state': 'pending'})
    elif task.state == 'SUCCESS':
        result = task.result or {}
        result['state'] = 'success'
        return jsonify(result)
    elif task.state == 'FAILURE':
        return jsonify({'state': 'failure', 'error': str(task.result)})
    elif task.state == 'PROGRESS':
        meta = task.info or {}
        return jsonify({
            'state':           'progress',
            'current':         meta.get('current', 0),
            'total':           meta.get('total', 0),
            'records_added':   meta.get('added', 0),
            'records_updated': meta.get('updated', 0),
            'records_skipped': meta.get('skipped', 0),
            'errors':          meta.get('errors', 0),
        })
    elif task.state == 'RETRY':
        exc_info = task.info
        err_msg = str(exc_info) if exc_info else 'unknown error'
        return jsonify({'state': 'retry', 'message': f'Task failed ({err_msg}) — retrying automatically. Click Sync All again to start fresh.'})
    else:
        return jsonify({'state': task.state.lower()})


def _resolve_conference_code(conference_name: str) -> str:
    """
    Look up the short code for a conference display name.
    Falls back to an empty string if not found.
    """
    if not conference_name:
        return ''
    from models import Conference
    try:
        conf = Conference.query.filter_by(display_name=conference_name).first()
        if conf:
            return conf.code
        # Try case-insensitive match
        conf = Conference.query.filter(
            db.func.lower(Conference.display_name) == conference_name.strip().lower()
        ).first()
        return conf.code if conf else ''
    except Exception:
        return ''


def _run_daily_sync(days_back: int = 1, dry_run: bool = False, celery_task=None) -> dict:
    """
    Core sync logic shared by the manual endpoint and Celery Beat task.

    Finds all completed jobs updated within `days_back` days, reads their
    output CSV files, and merges unique emails into MasterDatabase.

    Returns a summary dict.
    """
    from models import Job as JobModel

    cutoff   = datetime.utcnow() - timedelta(days=days_back)
    jobs     = JobModel.query.filter(
        JobModel.status    == 'completed',
        JobModel.end_time  >= cutoff,
        JobModel.output_file.isnot(None),
    ).all()

    total_added   = 0
    total_updated = 0
    total_skipped = 0
    jobs_processed = 0
    errors = []

    total_jobs = len(jobs)
    for job_idx, db_job in enumerate(jobs):
        try:
            if celery_task and job_idx % 5 == 0:
                try:
                    celery_task.update_state(
                        state='PROGRESS',
                        meta={
                            'current':  job_idx,
                            'total':    total_jobs,
                            'added':    total_added,
                            'updated':  total_updated,
                            'skipped':  total_skipped,
                            'errors':   len(errors),
                        }
                    )
                except Exception:
                    pass  # never let update_state crash the sync

            job = db_job.to_dict()
            output_file = job.get('output_file', '')
            if not output_file or not os.path.exists(output_file):
                jobs_processed += 1
                continue

            conf_name = job.get('conference', '') or job.get('conference_name', '')
            conf_code = _resolve_conference_code(conf_name)

            try:
                # ── Pass 1: read CSV into an in-memory dict (dedup by email) ──
                rows_dict = {}
                with open(output_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        email = (
                            row.get('Email') or row.get('email') or row.get('emails', '')
                        ).strip().lower()
                        if not email or '@' not in email or email == 'n/a':
                            total_skipped += 1
                            continue
                        if email in rows_dict:
                            total_skipped += 1
                            continue
                        csv_code = (row.get('Conference_Code') or
                                    row.get('conference_code', '')).strip().upper()
                        _aname = (row.get('Author_Name') or row.get('Name') or
                                  row.get('author_name') or row.get('full_name') or
                                  row.get('name') or row.get('author') or '')
                        if not _aname or _aname.upper() in ('N/A', 'NA', 'NONE', 'NULL'):
                            _fn = (row.get('first_name') or '').strip()
                            _ln = (row.get('last_name') or '').strip()
                            _aname = f'{_fn} {_ln}'.strip()
                        if _aname.upper() in ('N/A', 'NA', 'NONE', 'NULL'):
                            _aname = ''
                        rows_dict[email] = {
                            'author_name':    _aname,
                            'affiliation':    row.get('Affiliation') or row.get('affiliation', ''),
                            'article_url':    row.get('Article_URL') or row.get('URL') or row.get('Article URL', ''),
                            'article_title':  row.get('Title') or row.get('title', ''),
                            'conference_code': csv_code or conf_code,
                        }

                if not rows_dict:
                    jobs_processed += 1
                    continue

                all_emails = list(rows_dict.keys())

                if not dry_run:
                    from sqlalchemy.dialects.postgresql import insert as _pg_insert
                    _CHUNK = 2000
                    existing_set: set = set()
                    for ci in range(0, len(all_emails), _CHUNK):
                        chunk = all_emails[ci: ci + _CHUNK]
                        existing_set.update(
                            e for (e,) in
                            db.session.query(MasterDatabase.email)
                                      .filter(MasterDatabase.email.in_(chunk))
                                      .all()
                        )

                    to_insert    = []
                    journal_name = job.get('journal_name', '')
                    keyword_val  = job.get('keyword', '')
                    now          = datetime.utcnow()

                    for email, r in rows_dict.items():
                        if email in existing_set:
                            if r['author_name']:
                                db.session.query(MasterDatabase).filter(
                                    MasterDatabase.email == email,
                                    db.or_(MasterDatabase.author_name == None,
                                           MasterDatabase.author_name == ''),
                                ).update({'author_name': r['author_name'],
                                          'updated_at':  now},
                                         synchronize_session=False)
                            if r['conference_code']:
                                db.session.query(MasterDatabase).filter(
                                    MasterDatabase.email == email,
                                    db.or_(MasterDatabase.conference_code == None,
                                           MasterDatabase.conference_code == ''),
                                ).update({'conference_code': r['conference_code'],
                                          'updated_at':      now},
                                         synchronize_session=False)
                            total_updated += 1
                        else:
                            to_insert.append({
                                'id':              str(uuid.uuid4()),
                                'email':           email,
                                'author_name':     r['author_name'],
                                'affiliation':     r['affiliation'],
                                'article_url':     r['article_url'],
                                'article_title':   r['article_title'],
                                'conference_name': conf_name,
                                'conference_code': r['conference_code'],
                                'journal_name':    journal_name,
                                'keyword':         keyword_val,
                                'job_id':          str(db_job.id),
                                'scraped_date':    now,
                                'created_at':      now,
                                'updated_at':      now,
                            })
                            total_added += 1

                    if to_insert:
                        _IBATCH = 500
                        for _bi in range(0, len(to_insert), _IBATCH):
                            _batch = to_insert[_bi: _bi + _IBATCH]
                            stmt = _pg_insert(MasterDatabase.__table__).values(_batch)
                            stmt = stmt.on_conflict_do_nothing()
                            db.session.execute(stmt)

                    db.session.commit()
                    db.session.expunge_all()

                else:
                    existing_set = set(
                        e for (e,) in
                        db.session.query(MasterDatabase.email)
                                  .filter(MasterDatabase.email.in_(all_emails[:2000]))
                                  .all()
                    )
                    total_updated += sum(1 for e in all_emails if e in existing_set)
                    total_added   += sum(1 for e in all_emails if e not in existing_set)

                jobs_processed += 1

            except Exception as exc:
                db.session.rollback()
                db.session.expunge_all()
                try:
                    _jid = str(db_job.id)
                except Exception:
                    _jid = 'unknown'
                errors.append({'job_id': _jid, 'error': str(exc)[:200]})

        except Exception as outer_exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                _jid = str(db_job.id)
            except Exception:
                _jid = f'idx-{job_idx}'
            errors.append({'job_id': _jid, 'error': f'outer: {str(outer_exc)[:200]}'})

    return {
        'success':        True,
        'dry_run':        dry_run,
        'days_back':      days_back,
        'jobs_scanned':   len(jobs),
        'jobs_processed': jobs_processed,
        'records_added':  total_added,
        'records_updated': total_updated,
        'records_skipped': total_skipped,
        'errors':         errors,
        'synced_at':      datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/search')
@internal_user_required
def search_master_database():
    """Search master database with keyword, conference, and journal filters."""
    keyword    = request.args.get('keyword', '').strip()       # scraper search term
    author     = request.args.get('author', '').strip()        # author name or email
    conference = request.args.get('conference', '').strip()    # display name substring
    conf_code  = request.args.get('conference_code', '').strip().upper()  # exact code
    journal    = request.args.get('journal', '').strip()
    limit      = request.args.get('limit', 100, type=int)
    offset     = request.args.get('offset', 0, type=int)

    query = MasterDatabase.query

    if keyword:
        query = query.filter(MasterDatabase.keyword.ilike(f'%{keyword}%'))
    if author:
        query = query.filter(db.or_(
            MasterDatabase.author_name.ilike(f'%{author}%'),
            MasterDatabase.email.ilike(f'%{author}%'),
        ))
    if conf_code:
        query = query.filter(MasterDatabase.conference_code == conf_code)
    elif conference:
        query = query.filter(MasterDatabase.conference_name.ilike(f'%{conference}%'))
    if journal:
        query = query.filter(MasterDatabase.journal_name.ilike(f'%{journal}%'))

    total   = query.count()
    records = query.order_by(MasterDatabase.created_at.desc())\
                   .limit(limit).offset(offset).all()

    return jsonify({
        'total':   total,
        'limit':   limit,
        'offset':  offset,
        'records': [r.to_dict() for r in records],
    })


# ═══════════════════════════════════════════════════════════════════
# Download (admin only) — supports conference_code + keyword filters
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/download')
@admin_required
def download_master_database():
    """
    Admin only: Download master database as CSV or XLSX.

    Query params:
        format          csv | xlsx  (default: csv)
        conference_code short code, e.g. NWC  (optional, filters by code)
        conference      display-name substring  (optional)
        keyword         keyword substring        (optional)
    """
    file_format = request.args.get('format', 'csv')
    conf_code   = request.args.get('conference_code', '').strip().upper()
    conference  = request.args.get('conference', '').strip()
    keyword     = request.args.get('keyword', '').strip()

    query = MasterDatabase.query

    if conf_code:
        query = query.filter(MasterDatabase.conference_code == conf_code)
    elif conference:
        query = query.filter(MasterDatabase.conference_name.ilike(f'%{conference}%'))
    if keyword:
        query = query.filter(db.or_(
            MasterDatabase.keyword.ilike(f'%{keyword}%'),
            MasterDatabase.author_name.ilike(f'%{keyword}%'),
        ))

    records = query.order_by(MasterDatabase.created_at.desc()).all()

    # Build a descriptive filename suffix
    suffix_parts = []
    if conf_code:
        suffix_parts.append(conf_code)
    elif conference:
        suffix_parts.append(conference[:20].replace(' ', '_'))
    if keyword:
        suffix_parts.append(keyword[:20].replace(' ', '_'))
    suffix_parts.append(datetime.now().strftime('%Y%m%d_%H%M%S'))
    file_suffix = '_'.join(suffix_parts)

    fieldnames = [
        'author_name', 'email', 'affiliation',
        'conference_name', 'conference_code',
        'journal_name', 'article_title', 'article_url',
        'keyword', 'scraped_date', 'created_at',
    ]

    if file_format == 'xlsx':
        data = [r.to_dict() for r in records]
        df   = pd.DataFrame(data)
        # Ensure all expected columns exist
        for col in fieldnames:
            if col not in df.columns:
                df[col] = ''
        df = df[[c for c in fieldnames if c in df.columns]]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Master Database', index=False)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'master_database_{file_suffix}.xlsx',
        )

    # CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        row = record.to_dict()
        writer.writerow({k: row.get(k, '') for k in fieldnames})
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'master_database_{file_suffix}.csv',
    )


# ═══════════════════════════════════════════════════════════════════
# Stats (admin only) — extended with per-conference + per-keyword breakdown
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/stats')
@admin_required
def master_database_stats():
    """
    Admin-only statistics view for the master database.

    Returns:
      • total_records, unique_conferences, unique_journals
      • recent_records  — last 10 additions
      • top_conferences — top 10 by record count (includes display name)
      • top_keywords    — top 10 keywords
      • daily_additions — record count per day for the last 30 days
      • conference_breakdown — every conference with its count and last-updated date
    """
    from models import Conference

    total_records       = MasterDatabase.query.count()
    unique_conferences  = db.session.query(MasterDatabase.conference_name)\
                            .distinct()\
                            .filter(MasterDatabase.conference_name != '')\
                            .count()
    unique_journals     = db.session.query(MasterDatabase.journal_name)\
                            .distinct()\
                            .filter(MasterDatabase.journal_name != '')\
                            .count()

    recent_records = MasterDatabase.query\
                        .order_by(MasterDatabase.created_at.desc())\
                        .limit(10).all()

    # Top conferences by record count — join with Conference for display name
    conf_counts = db.session.query(
        MasterDatabase.conference_code,
        MasterDatabase.conference_name,
        db.func.count(MasterDatabase.id).label('count'),
        db.func.max(MasterDatabase.updated_at).label('last_updated'),
    ).filter(MasterDatabase.conference_name != '')\
     .group_by(MasterDatabase.conference_code, MasterDatabase.conference_name)\
     .order_by(db.text('count DESC'))\
     .limit(10).all()

    top_conferences = []
    for row in conf_counts:
        # Try to get the canonical display name from the Conference table
        conf_obj  = Conference.query.filter_by(code=row.conference_code).first() if row.conference_code else None
        top_conferences.append({
            'conference_code': row.conference_code or '',
            'conference':      conf_obj.display_name if conf_obj else row.conference_name,
            'count':           row.count,
            'last_updated':    row.last_updated.isoformat() if row.last_updated else None,
        })

    # Top keywords
    kw_counts = db.session.query(
        MasterDatabase.keyword,
        db.func.count(MasterDatabase.id).label('count'),
    ).filter(MasterDatabase.keyword != '')\
     .group_by(MasterDatabase.keyword)\
     .order_by(db.text('count DESC'))\
     .limit(10).all()
    top_keywords = [{'keyword': k[0], 'count': k[1]} for k in kw_counts]

    # Daily additions — last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_raw = db.session.query(
        db.func.date(MasterDatabase.created_at).label('day'),
        db.func.count(MasterDatabase.id).label('count'),
    ).filter(MasterDatabase.created_at >= thirty_days_ago)\
     .group_by(db.func.date(MasterDatabase.created_at))\
     .order_by(db.text('day ASC'))\
     .all()
    daily_additions = [{'date': str(r.day), 'count': r.count} for r in daily_raw]

    # Full conference breakdown (all active conferences + their counts)
    all_active_conferences = Conference.query.filter_by(is_active=True)\
                                             .order_by(Conference.display_name).all()
    conference_breakdown = []
    for conf in all_active_conferences:
        count = MasterDatabase.query.filter_by(conference_code=conf.code).count()
        last_record = MasterDatabase.query\
                        .filter_by(conference_code=conf.code)\
                        .order_by(MasterDatabase.updated_at.desc())\
                        .first()
        conference_breakdown.append({
            'code':         conf.code,
            'display_name': conf.display_name,
            'total_records': count,
            'last_updated': (
                last_record.updated_at.isoformat()
                if last_record and last_record.updated_at else None
            ),
        })

    last_synced_at = db.session.query(db.func.max(MasterDatabase.updated_at)).scalar()

    return jsonify({
        'total_records':        total_records,
        'unique_conferences':   unique_conferences,
        'unique_journals':      unique_journals,
        'recent_records':       [r.to_dict() for r in recent_records],
        'top_conferences':      top_conferences,
        'top_keywords':         top_keywords,
        'daily_additions':      daily_additions,
        'conference_breakdown': conference_breakdown,
        'last_synced_at':       last_synced_at.isoformat() if last_synced_at else None,
    })


# ═══════════════════════════════════════════════════════════════════
# Journals dropdown (distinct journal_name values in the master DB)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/journals')
@internal_user_required
def master_db_journals():
    """Return the known scraper/journal names (matches what Job.journal_name stores)."""
    # These values match JOURNALS[key]['name'] in app.py — the exact strings
    # written to Job.journal_name when a job is created.
    journals = [
        'BMJ Journals',
        'Cambridge University Press',
        'Emerald Insight',
        'Europe PMC',
        'Lippincott',
        'MDPI',
        'Nature',
        'OnlineWiley',
        'Oxford Academic',
        'PDF Scraper',
        'PubMed',
        'SAGE Journals',
        'Science Direct',
        'Springer',
        'TandFonline',
    ]
    return jsonify({'journals': sorted(journals)})


# ═══════════════════════════════════════════════════════════════════
# Clear master database (admin only)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/master-database/clear', methods=['POST'])
@admin_required
def clear_master_database():
    """Wipe all rows from master_database. Admin only."""
    try:
        count = db.session.query(MasterDatabase).count()
        db.session.query(MasterDatabase).delete(synchronize_session=False)
        db.session.commit()
        # Also clear the Redis sync lock so a fresh sync can be dispatched
        try:
            r = _get_redis()
            r.delete(_SYNC_LOCK_KEY)
        except Exception:
            pass
        return jsonify({'success': True, 'deleted': count})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# Conference master list (unchanged from original)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/conference-master/list')
@internal_user_required
def list_conference_masters():
    """List uploaded conference master data."""
    conference = request.args.get('conference', '').strip()
    limit      = request.args.get('limit', 100, type=int)

    query = ConferenceMaster.query
    if conference:
        query = query.filter(ConferenceMaster.conference_name.ilike(f'%{conference}%'))

    records = query.order_by(ConferenceMaster.upload_date.desc()).limit(limit).all()
    return jsonify({'records': [r.to_dict() for r in records], 'total': query.count()})


# ═══════════════════════════════════════════════════════════════════
# Public conferences dropdown (used by job-submission UI)
# ═══════════════════════════════════════════════════════════════════

@master_db_bp.route('/api/conferences')
def conferences_list():
    """
    Returns active conferences that the current user is allowed to select.
    Used to populate the conference dropdown in the job-submission form.
    Auth: session required.
    """
    from models import Conference

    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    all_active = Conference.query.filter_by(is_active=True)\
                                 .order_by(Conference.display_name).all()

    allowed_raw = getattr(user, 'allowed_conferences', 'all') or 'all'
    if allowed_raw == 'all':
        visible = all_active
    else:
        try:
            import json
            allowed_codes = set(json.loads(allowed_raw))
        except (ValueError, TypeError):
            allowed_codes = set()
        visible = [c for c in all_active if c.code in allowed_codes]

    return jsonify({
        'conferences': [
            {'code': c.code, 'display_name': c.display_name}
            for c in visible
        ]
    })