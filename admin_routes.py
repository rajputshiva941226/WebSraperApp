"""
Admin Panel Routes - User Management
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from models import db, User, _hash_password
from functools import wraps
import json as _json

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
        session['user_type'] = user.user_type
        session['credits'] = user.credits
        session['email'] = user.email

    if request.is_json:
        return jsonify({'success': True, 'message': f'User {user.username} updated successfully'})
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users,
        message=f'User {user.username} updated successfully', message_type='success')


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
