"""
Master Database Routes
Handles master database operations, conference data upload, and auto-append logic
"""

from flask import Blueprint, request, jsonify, render_template, send_file
from models import db, MasterDatabase, ConferenceMaster, User
from auth import admin_required, internal_user_required, get_current_user
from werkzeug.utils import secure_filename
import os
import csv
import pandas as pd
from datetime import datetime
import io

master_db_bp = Blueprint('master_db', __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@master_db_bp.route('/master-database')
@internal_user_required
def master_database_page():
    """Master database management page (internal users only)"""
    return render_template('master_database.html')


@master_db_bp.route('/api/master-database/upload', methods=['POST'])
@internal_user_required
def upload_conference_data():
    """
    Upload conference master data (internal users only)
    Expects CSV/XLSX with columns: author_name, email, affiliation (optional)
    """
    user = get_current_user()
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file format. Use CSV or XLSX'}), 400
    
    # Get conference info from form
    conference_name = request.form.get('conference_name')
    conference_year = request.form.get('conference_year', type=int)
    conference_location = request.form.get('conference_location', '')
    
    if not conference_name:
        return jsonify({'error': 'Conference name is required'}), 400
    
    # Read file
    try:
        filename = secure_filename(file.filename)
        
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Validate columns
        required_columns = ['author_name', 'email']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400
        
        # Process records
        records_added = 0
        records_updated = 0
        records_skipped = 0
        
        for _, row in df.iterrows():
            email = str(row['email']).strip().lower()
            author_name = str(row['author_name']).strip()
            affiliation = str(row.get('affiliation', '')).strip() if 'affiliation' in row else ''
            
            if not email or '@' not in email:
                records_skipped += 1
                continue
            
            # Check if exists
            existing = ConferenceMaster.query.filter_by(
                conference_name=conference_name,
                email=email
            ).first()
            
            if existing:
                # Update existing record
                existing.author_name = author_name
                existing.affiliation = affiliation
                existing.conference_year = conference_year
                existing.conference_location = conference_location
                records_updated += 1
            else:
                # Create new record
                record = ConferenceMaster(
                    conference_name=conference_name,
                    conference_year=conference_year,
                    conference_location=conference_location,
                    author_name=author_name,
                    email=email,
                    affiliation=affiliation,
                    uploaded_by=user.id,
                    source_file=filename
                )
                db.session.add(record)
                records_added += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Upload complete',
            'records_added': records_added,
            'records_updated': records_updated,
            'records_skipped': records_skipped,
            'total_processed': records_added + records_updated + records_skipped
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500


@master_db_bp.route('/api/master-database/append-scraped', methods=['POST'])
@internal_user_required
def append_scraped_results():
    """
    Auto-append scraped results to master database
    Deduplicates based on email
    """
    data = request.json
    job_id = data.get('job_id')
    
    if not job_id:
        return jsonify({'error': 'Job ID is required'}), 400
    
    # Import from app.py context
    from app import active_jobs, job_history
    
    # Find job
    job = active_jobs.get(job_id)
    if not job:
        for hist_job in job_history:
            if hist_job.get('id') == job_id:
                job = hist_job
                break
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    output_file = job.get('output_file')
    if not output_file or not os.path.exists(output_file):
        return jsonify({'error': 'Output file not found'}), 404
    
    # Read CSV and append to master database
    try:
        records_added = 0
        records_updated = 0
        records_skipped = 0
        
        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Extract fields (handle different column names)
                email = row.get('Email') or row.get('email') or row.get('emails', '')
                author_name = row.get('Author_Name') or row.get('Name') or row.get('author_name') or row.get('Names', '')
                affiliation = row.get('Affiliation') or row.get('affiliation', '')
                article_url = row.get('Article_URL') or row.get('URL') or row.get('Article URL', '')
                article_title = row.get('Title') or row.get('title', '')
                
                email = email.strip().lower()
                if not email or '@' not in email or email == 'n/a':
                    records_skipped += 1
                    continue
                
                # Check if exists in master database
                existing = MasterDatabase.query.filter_by(email=email).first()
                
                if existing:
                    # Update existing record with new info
                    existing.author_name = author_name
                    existing.affiliation = affiliation or existing.affiliation
                    existing.article_url = article_url or existing.article_url
                    existing.article_title = article_title or existing.article_title
                    existing.updated_at = datetime.utcnow()
                    records_updated += 1
                else:
                    # Create new record
                    record = MasterDatabase(
                        author_name=author_name,
                        email=email,
                        affiliation=affiliation,
                        conference_name=job.get('conference_name', ''),
                        journal_name=job.get('journal_name', ''),
                        article_title=article_title,
                        article_url=article_url,
                        keyword=job.get('keyword', ''),
                        job_id=job_id
                    )
                    db.session.add(record)
                    records_added += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Results appended to master database',
            'records_added': records_added,
            'records_updated': records_updated,
            'records_skipped': records_skipped,
            'total_processed': records_added + records_updated + records_skipped
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to append results: {str(e)}'}), 500


@master_db_bp.route('/api/master-database/search')
@internal_user_required
def search_master_database():
    """Search master database with filters"""
    keyword = request.args.get('keyword', '').strip()
    conference = request.args.get('conference', '').strip()
    journal = request.args.get('journal', '').strip()
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = MasterDatabase.query
    
    if keyword:
        query = query.filter(
            db.or_(
                MasterDatabase.author_name.ilike(f'%{keyword}%'),
                MasterDatabase.email.ilike(f'%{keyword}%'),
                MasterDatabase.keyword.ilike(f'%{keyword}%')
            )
        )
    
    if conference:
        query = query.filter(MasterDatabase.conference_name.ilike(f'%{conference}%'))
    
    if journal:
        query = query.filter(MasterDatabase.journal_name.ilike(f'%{journal}%'))
    
    total = query.count()
    records = query.order_by(MasterDatabase.created_at.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()
    
    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'records': [r.to_dict() for r in records]
    })


@master_db_bp.route('/api/master-database/download')
@admin_required
def download_master_database():
    """Admin only: Download entire master database"""
    file_format = request.args.get('format', 'csv')
    
    # Get all records
    records = MasterDatabase.query.order_by(MasterDatabase.created_at.desc()).all()
    
    if file_format == 'xlsx':
        # Create Excel file
        data = [r.to_dict() for r in records]
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Master Database', index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'master_database_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    
    else:
        # Create CSV file
        output = io.StringIO()
        if records:
            fieldnames = ['author_name', 'email', 'affiliation', 'conference_name', 
                         'journal_name', 'article_title', 'article_url', 'keyword', 
                         'scraped_date', 'created_at']
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
            download_name=f'master_database_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )


@master_db_bp.route('/api/master-database/stats')
@internal_user_required
def master_database_stats():
    """Get master database statistics"""
    total_records = MasterDatabase.query.count()
    unique_conferences = db.session.query(MasterDatabase.conference_name)\
        .distinct()\
        .filter(MasterDatabase.conference_name != '')\
        .count()
    unique_journals = db.session.query(MasterDatabase.journal_name)\
        .distinct()\
        .filter(MasterDatabase.journal_name != '')\
        .count()
    
    # Recent additions
    recent_records = MasterDatabase.query\
        .order_by(MasterDatabase.created_at.desc())\
        .limit(10)\
        .all()
    
    # Conference breakdown
    conference_counts = db.session.query(
        MasterDatabase.conference_name,
        db.func.count(MasterDatabase.id).label('count')
    ).filter(MasterDatabase.conference_name != '')\
     .group_by(MasterDatabase.conference_name)\
     .order_by(db.text('count DESC'))\
     .limit(10)\
     .all()
    
    return jsonify({
        'total_records': total_records,
        'unique_conferences': unique_conferences,
        'unique_journals': unique_journals,
        'recent_records': [r.to_dict() for r in recent_records],
        'top_conferences': [{'conference': c[0], 'count': c[1]} for c in conference_counts]
    })


@master_db_bp.route('/api/conference-master/list')
@internal_user_required
def list_conference_masters():
    """List uploaded conference master data"""
    conference = request.args.get('conference', '').strip()
    limit = request.args.get('limit', 100, type=int)
    
    query = ConferenceMaster.query
    
    if conference:
        query = query.filter(ConferenceMaster.conference_name.ilike(f'%{conference}%'))
    
    records = query.order_by(ConferenceMaster.upload_date.desc())\
        .limit(limit)\
        .all()
    
    return jsonify({
        'records': [r.to_dict() for r in records],
        'total': query.count()
    })
