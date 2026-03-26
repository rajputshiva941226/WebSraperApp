"""
Admin Panel Routes - User Management
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from models import db, User, Conference, _hash_password
from functools import wraps
import json as _json
import uuid
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        if session.get('user_type') != 'admin':
            return "Access Denied: Admin privileges required", 403
        
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/')
@admin_required
def admin_panel():
    """Admin dashboard with user management"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users)


@admin_bp.route('/create-user', methods=['POST'])
@admin_required
def create_user():
    """Create a new user"""
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    user_type = request.form.get('user_type', 'external')
    credits = request.form.get('credits', 100, type=int)
    
    # Check if user exists
    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin.html', users=users, 
            message='Username or email already exists', message_type='error')
    
    # Get allowed scrapers
    import json
    scrapers = request.form.getlist('scrapers')
    all_scrapers = request.form.get('all_scrapers') == 'on'
    if all_scrapers or not scrapers:
        allowed_scrapers = 'all'
    else:
        allowed_scrapers = json.dumps(scrapers)

    license_type = request.form.get('license_type', 'multi')
    if license_type not in ('single', 'multi'):
        license_type = 'multi'

    # Create user
    new_user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password),
        user_type=user_type,
        credits=credits,
        license_type=license_type,
        is_active=True,
        is_verified=True,
        allowed_scrapers=allowed_scrapers
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users, 
        message=f'User {username} created successfully!', message_type='success')


@admin_bp.route('/add-credits', methods=['POST'])
@admin_required
def add_credits():
    """Add or deduct credits from a user with transaction logging"""
    user_id = request.form.get('user_id') or (request.json or {}).get('user_id')
    amount_raw = request.form.get('amount') or (request.json or {}).get('amount')
    reason = request.form.get('reason') or (request.json or {}).get('reason', 'Admin adjustment')

    try:
        amount = int(amount_raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    from models import CreditTransaction
    transaction = CreditTransaction(
        user_id=user.id,
        amount=amount,
        transaction_type='admin_adjustment',
        description=f'{reason} (by admin: {session.get("username")})'
    )
    user.credits += amount
    db.session.add(transaction)
    db.session.commit()

    if session.get('user_id') == user_id:
        session['credits'] = user.credits

    action = 'Added' if amount > 0 else 'Deducted'
    if request.is_json:
        return jsonify({'success': True, 'message': f'{action} {abs(amount)} credits for {user.username}', 'new_credits': user.credits})
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users,
        message=f'{action} {abs(amount)} credits for {user.username}', message_type='success')


@admin_bp.route('/toggle-user/<user_id>')
@admin_required
def toggle_user(user_id):
    """Enable or disable a user"""
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))
    
    # Prevent disabling the last admin
    if user.user_type == 'admin' and user.is_active:
        admin_count = User.query.filter_by(user_type='admin', is_active=True).count()
        if admin_count <= 1:
            users = User.query.order_by(User.created_at.desc()).all()
            return render_template('admin.html', users=users, 
                message='Cannot disable the last active admin', message_type='error')
    
    user.is_active = not user.is_active
    db.session.commit()
    
    # Log out user if they're being disabled and currently logged in
    if not user.is_active and session.get('user_id') == user_id:
        session.clear()
        return redirect(url_for('auth.login'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    status = 'enabled' if user.is_active else 'disabled'
    return render_template('admin.html', users=users, 
        message=f'User {user.username} {status}', message_type='success')


@admin_bp.route('/manage-scrapers', methods=['POST'])
@admin_required
def manage_scrapers():
    """Update user's allowed scrapers"""
    if request.is_json:
        data = request.json
        user_id = data.get('user_id')
        scrapers = data.get('scrapers', [])
        all_scrapers = data.get('all_scrapers', False)
    else:
        user_id = request.form.get('user_id')
        scrapers = request.form.getlist('scrapers')
        all_scrapers = request.form.get('all_scrapers') == 'on'

    user = User.query.get(user_id)
    if not user:
        if request.is_json:
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('admin.admin_panel'))

    user.allowed_scrapers = 'all' if (all_scrapers or not scrapers) else _json.dumps(scrapers)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'message': f'Updated scraper permissions for {user.username}'})
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users,
        message=f'Updated scraper permissions for {user.username}', message_type='success')


@admin_bp.route('/edit-user', methods=['POST'])
@admin_required
def edit_user():
    """Edit user details: username, email, password, user_type, license_type, credits"""
    if request.is_json:
        data = request.json
    else:
        data = request.form

    user_id = data.get('user_id')
    user = User.query.get(user_id)
    if not user:
        if request.is_json:
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('admin.admin_panel'))

    new_username = data.get('username', '').strip()
    new_email = data.get('email', '').strip()
    new_password = data.get('password', '').strip()
    new_user_type = data.get('user_type', user.user_type)
    new_license_type = data.get('license_type', user.license_type)
    new_credits = data.get('credits')

    # Validate uniqueness
    if new_username and new_username != user.username:
        if User.query.filter(User.username == new_username, User.id != user_id).first():
            if request.is_json:
                return jsonify({'error': 'Username already taken'}), 400
            users = User.query.order_by(User.created_at.desc()).all()
            return render_template('admin.html', users=users, message='Username already taken', message_type='error')
        user.username = new_username

    if new_email and new_email != user.email:
        if User.query.filter(User.email == new_email, User.id != user_id).first():
            if request.is_json:
                return jsonify({'error': 'Email already taken'}), 400
            users = User.query.order_by(User.created_at.desc()).all()
            return render_template('admin.html', users=users, message='Email already taken', message_type='error')
        user.email = new_email

    if new_password and len(new_password) >= 8:
        user.password_hash = _hash_password(new_password)

    if new_user_type in ('admin', 'internal', 'external'):
        user.user_type = new_user_type

    if new_license_type in ('single', 'multi'):
        user.license_type = new_license_type
        if new_license_type == 'multi':
            user.machine_id = None  # Clear machine lock for multi-license

    if new_credits is not None:
        try:
            user.credits = int(new_credits)
        except (TypeError, ValueError):
            pass

    db.session.commit()

    # Update session if editing self
    if session.get('user_id') == user_id:
        session['username'] = user.username
        session['email'] = user.email
        session['user_type'] = user.user_type

    if request.is_json:
        return jsonify({'success': True, 'message': f'User {user.username} updated successfully'})
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users,
        message=f'User {user.username} updated successfully', message_type='success')


# ── Conference Management Routes ──

@admin_bp.route('/conferences')
@admin_required
def manage_conferences():
    """Admin page for managing conferences"""
    conferences = Conference.query.order_by(Conference.name).all()
    users = User.query.filter_by(user_type='external').order_by(User.username).all()
    return render_template('admin_conferences.html', conferences=conferences, users=users)


@admin_bp.route('/api/conferences/list', methods=['GET'])
@admin_required
def list_all_conferences():
    """Get all conferences with user assignments"""
    try:
        # Get all conferences regardless of active status
        conferences = Conference.query.order_by(Conference.name).all()
        print(f"[DEBUG] Found {len(conferences)} conferences in database")
        
        result = []
        for conf in conferences:
            try:
                assigned_users = conf.assigned_users.all()
                result.append({
                    'id': conf.id,
                    'name': conf.name,
                    'short_form': conf.short_form,
                    'display_name': conf.display_name,
                    'description': conf.description,
                    'year': conf.year,
                    'location': conf.location,
                    'is_active': conf.is_active,
                    'assigned_users_count': len(assigned_users),
                    'assigned_users': [{'id': u.id, 'username': u.username, 'email': u.email} for u in assigned_users],
                    'created_at': conf.created_at.isoformat() if conf.created_at else None
                })
            except Exception as e:
                print(f"[DEBUG] Error processing conference {conf.id}: {e}")
                continue
        
        print(f"[DEBUG] Returning {len(result)} conferences")
        return jsonify({'conferences': result, 'total': len(result)})
    except Exception as e:
        print(f"[DEBUG] Error in list_all_conferences: {e}")
        return jsonify({'error': str(e), 'conferences': [], 'total': 0}), 500


@admin_bp.route('/api/conferences/mappings', methods=['GET'])
@admin_required
def get_conference_mappings():
    """Get all available conference short form to full form mappings"""
    from conference_config import get_all_conferences
    mappings = get_all_conferences()
    return jsonify({'mappings': mappings, 'total': len(mappings)})


@admin_bp.route('/api/conferences/create', methods=['POST'])
@admin_required
def create_conference_admin():
    """Create a new conference"""
    data = request.json
    
    name = data.get('name', '').strip()
    short_form = data.get('short_form', '').strip()
    display_name = data.get('display_name', '').strip()
    description = data.get('description', '').strip()
    year = data.get('year')
    location = data.get('location', '').strip()
    
    if not name:
        return jsonify({'error': 'Conference name is required'}), 400
    
    # Check if exists
    if Conference.query.filter_by(name=name).first():
        return jsonify({'error': 'Conference already exists'}), 400
    
    if short_form and Conference.query.filter_by(short_form=short_form).first():
        return jsonify({'error': 'Short form already exists'}), 400
    
    user = User.query.get(session.get('user_id'))
    conference = Conference(
        id=str(uuid.uuid4()),
        name=name,
        short_form=short_form or None,
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
        'message': f'Conference "{name}" created',
        'conference': {
            'id': conference.id,
            'name': conference.name,
            'short_form': conference.short_form,
            'display_name': conference.display_name,
            'description': conference.description,
            'year': conference.year,
            'location': conference.location,
            'is_active': conference.is_active
        }
    }), 201


@admin_bp.route('/api/conferences/<conference_id>/assign-users', methods=['POST'])
@admin_required
def assign_users_admin(conference_id):
    """Assign users to a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    data = request.json
    user_ids = data.get('user_ids', [])
    
    if not user_ids:
        return jsonify({'error': 'No users provided'}), 400
    
    assigned_count = 0
    for user_id in user_ids:
        user = User.query.get(user_id)
        if user and user not in conference.assigned_users:
            conference.assigned_users.append(user)
            assigned_count += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Assigned {assigned_count} user(s)',
        'assigned_count': assigned_count
    })


@admin_bp.route('/api/conferences/<conference_id>/remove-user/<user_id>', methods=['POST'])
@admin_required
def remove_user_admin(conference_id, user_id):
    """Remove user from conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user in conference.assigned_users:
        conference.assigned_users.remove(user)
        db.session.commit()
    
    return jsonify({'success': True, 'message': 'User removed'})


@admin_bp.route('/api/conferences/<conference_id>/delete', methods=['POST'])
@admin_required
def delete_conference_admin(conference_id):
    """Delete a conference"""
    conference = Conference.query.get(conference_id)
    if not conference:
        return jsonify({'error': 'Conference not found'}), 404
    
    name = conference.name
    db.session.delete(conference)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Conference "{name}" deleted'})


@admin_bp.route('/delete-user/<user_id>')
@admin_required
def delete_user(user_id):
    """Delete a user (soft delete or hard delete)"""
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))
    
    # Prevent deleting the last admin
    if user.user_type == 'admin':
        admin_count = User.query.filter_by(user_type='admin').count()
        if admin_count <= 1:
            users = User.query.order_by(User.created_at.desc()).all()
            return render_template('admin.html', users=users, 
                message='Cannot delete the last admin', message_type='error')
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users, 
        message=f'User {username} deleted', message_type='success')
