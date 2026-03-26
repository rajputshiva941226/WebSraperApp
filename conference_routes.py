"""
Conference Management Routes
Handles conference CRUD, user-conference assignments, and conference-specific data queries
"""

from flask import Blueprint, request, jsonify, render_template
from models import db, Conference, ConferenceScrapeData, User, user_conference
from auth import admin_required, login_required, get_current_user
from datetime import datetime
import uuid

conference_bp = Blueprint('conference', __name__, url_prefix='/api/conference')


@conference_bp.route('/list', methods=['GET'])
@login_required
def list_conferences():
    """List all active conferences"""
    user = get_current_user()
    is_admin = user.user_type == 'admin'
    
    try:
        if is_admin:
            # Admin sees all conferences (including inactive)
            conferences = Conference.query.order_by(Conference.name).all()
            print(f"[DEBUG] Admin user - found {len(conferences)} total conferences")
        else:
            # Regular users see only their assigned conferences
            conferences = user.assigned_conferences.order_by(Conference.name).all()
            print(f"[DEBUG] Regular user - found {len(conferences)} assigned conferences")
        
        result = []
        for c in conferences:
            conf_dict = c.to_dict()
            # Include both short form (for filenames) and full form (for display)
            conf_dict['filename_form'] = c.short_form or c.name
            result.append(conf_dict)
        
        print(f"[DEBUG] Returning {len(result)} conferences")
        return jsonify({
            'conferences': result,
            'total': len(result)
        })
    except Exception as e:
        print(f"[DEBUG] Error in list_conferences: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'conferences': [],
            'total': 0
        }), 500


@conference_bp.route('/create', methods=['POST'])
@admin_required
def create_conference():
    """Admin: Create a new conference"""
    data = request.json
    
    name = data.get('name', '').strip()
    display_name = data.get('display_name', '').strip()
    description = data.get('description', '').strip()
    year = data.get('year', type=int)
    location = data.get('location', '').strip()
    
    if not name:
        return jsonify({'error': 'Conference name is required'}), 400
    
    # Check if conference already exists
    existing = Conference.query.filter_by(name=name).first()
    if existing:
        return jsonify({'error': 'Conference with this name already exists'}), 400
    
    user = get_current_user()
    conference = Conference(
        id=str(uuid.uuid4()),
        name=name,
        display_name=display_name or name,
        description=description,
        year=year,
        location=location,
        is_active=True,
        created_by=user.id,
        created_at=datetime.utcnow()
    )
    
    db.session.add(conference)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Conference "{name}" created successfully',
        'conference': conference.to_dict()
    }), 201


@conference_bp.route('/<conference_id>', methods=['GET'])
@login_required
def get_conference(conference_id):
    """Get conference details"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = get_current_user()
    # Check access: admin or assigned user
    if user.user_type != 'admin' and conference not in user.assigned_conferences:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(conference.to_dict())


@conference_bp.route('/<conference_id>/update', methods=['POST'])
@admin_required
def update_conference(conference_id):
    """Admin: Update conference details"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    data = request.json
    
    if 'name' in data:
        conference.name = data['name'].strip()
    if 'display_name' in data:
        conference.display_name = data['display_name'].strip()
    if 'description' in data:
        conference.description = data['description'].strip()
    if 'year' in data:
        conference.year = data['year']
    if 'location' in data:
        conference.location = data['location'].strip()
    if 'is_active' in data:
        conference.is_active = data['is_active']
    
    conference.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Conference updated successfully',
        'conference': conference.to_dict()
    })


@conference_bp.route('/<conference_id>/assign-users', methods=['POST'])
@admin_required
def assign_users_to_conference(conference_id):
    """Admin: Assign users to a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    data = request.json
    user_ids = data.get('user_ids', [])
    
    if not user_ids:
        return jsonify({'error': 'No users provided'}), 400
    
    assigned_count = 0
    errors = []
    
    for user_id in user_ids:
        user = User.query.get(user_id)
        if not user:
            errors.append(f'User {user_id} not found')
            continue
        
        # Check if already assigned
        if user not in conference.assigned_users:
            conference.assigned_users.append(user)
            assigned_count += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Assigned {assigned_count} user(s) to conference',
        'assigned_count': assigned_count,
        'errors': errors if errors else None
    })


@conference_bp.route('/<conference_id>/remove-user/<user_id>', methods=['POST'])
@admin_required
def remove_user_from_conference(conference_id, user_id):
    """Admin: Remove user from a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user in conference.assigned_users:
        conference.assigned_users.remove(user)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'User removed from conference'
    })


@conference_bp.route('/<conference_id>/users', methods=['GET'])
@admin_required
def get_conference_users(conference_id):
    """Admin: Get users assigned to a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    users = conference.assigned_users.all()
    
    return jsonify({
        'conference_id': conference_id,
        'conference_name': conference.name,
        'users': [{'id': u.id, 'username': u.username, 'email': u.email, 'user_type': u.user_type} for u in users],
        'total': len(users)
    })


@conference_bp.route('/<conference_id>/scrape-data', methods=['GET'])
@login_required
def get_conference_scrape_data(conference_id):
    """Get scrape data for a conference with filtering"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = get_current_user()
    # Check access
    if user.user_type != 'admin' and conference not in user.assigned_conferences:
        return jsonify({'error': 'Access denied'}), 403
    
    # Query parameters for filtering
    keyword = request.args.get('keyword', '').strip()
    journal_scraper = request.args.get('journal_scraper', '').strip()
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = ConferenceScrapeData.query.filter_by(conference_id=conference_id)
    
    if keyword:
        query = query.filter(
            db.or_(
                ConferenceScrapeData.keyword.ilike(f'%{keyword}%'),
                ConferenceScrapeData.author_name.ilike(f'%{keyword}%'),
                ConferenceScrapeData.email.ilike(f'%{keyword}%')
            )
        )
    
    if journal_scraper:
        query = query.filter(ConferenceScrapeData.journal_scraper.ilike(f'%{journal_scraper}%'))
    
    total = query.count()
    records = query.order_by(ConferenceScrapeData.scraped_at.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()
    
    return jsonify({
        'conference_id': conference_id,
        'conference_name': conference.name,
        'total': total,
        'limit': limit,
        'offset': offset,
        'records': [r.to_dict() for r in records]
    })


@conference_bp.route('/<conference_id>/stats', methods=['GET'])
@login_required
def get_conference_stats(conference_id):
    """Get statistics for a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = get_current_user()
    # Check access
    if user.user_type != 'admin' and conference not in user.assigned_conferences:
        return jsonify({'error': 'Access denied'}), 403
    
    # Total records
    total_records = ConferenceScrapeData.query.filter_by(conference_id=conference_id).count()
    
    # Unique emails
    unique_emails = db.session.query(db.func.count(db.distinct(ConferenceScrapeData.email)))\
        .filter(ConferenceScrapeData.conference_id == conference_id).scalar() or 0
    
    # Unique authors
    unique_authors = db.session.query(db.func.count(db.distinct(ConferenceScrapeData.author_name)))\
        .filter(ConferenceScrapeData.conference_id == conference_id).scalar() or 0
    
    # Unique articles
    unique_articles = db.session.query(db.func.count(db.distinct(ConferenceScrapeData.article_url)))\
        .filter(ConferenceScrapeData.conference_id == conference_id).scalar() or 0
    
    # Journal breakdown
    journal_counts = db.session.query(
        ConferenceScrapeData.journal_scraper,
        db.func.count(ConferenceScrapeData.id).label('count')
    ).filter(ConferenceScrapeData.conference_id == conference_id)\
     .group_by(ConferenceScrapeData.journal_scraper)\
     .order_by(db.text('count DESC'))\
     .all()
    
    # Keyword breakdown
    keyword_counts = db.session.query(
        ConferenceScrapeData.keyword,
        db.func.count(ConferenceScrapeData.id).label('count')
    ).filter(ConferenceScrapeData.conference_id == conference_id)\
     .group_by(ConferenceScrapeData.keyword)\
     .order_by(db.text('count DESC'))\
     .limit(10)\
     .all()
    
    return jsonify({
        'conference_id': conference_id,
        'conference_name': conference.name,
        'total_records': total_records,
        'unique_emails': unique_emails,
        'unique_authors': unique_authors,
        'unique_articles': unique_articles,
        'journal_breakdown': [{'journal': j[0], 'count': j[1]} for j in journal_counts],
        'top_keywords': [{'keyword': k[0], 'count': k[1]} for k in keyword_counts]
    })


@conference_bp.route('/<conference_id>/export', methods=['GET'])
@login_required
def export_conference_data(conference_id):
    """Export conference scrape data as CSV or XLSX"""
    import io
    import csv
    import pandas as pd
    from flask import send_file
    
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = get_current_user()
    # Check access
    if user.user_type != 'admin' and conference not in user.assigned_conferences:
        return jsonify({'error': 'Access denied'}), 403
    
    file_format = request.args.get('format', 'csv').lower()
    
    # Get all records for this conference
    records = ConferenceScrapeData.query.filter_by(conference_id=conference_id)\
        .order_by(ConferenceScrapeData.scraped_at.desc()).all()
    
    if not records:
        return jsonify({'error': 'No data to export'}), 404
    
    data = [r.to_dict() for r in records]
    
    if file_format == 'xlsx':
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Scrape Data', index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{conference.name}_scrape_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    else:
        # CSV format
        output = io.StringIO()
        if data:
            fieldnames = list(data[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{conference.name}_scrape_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
