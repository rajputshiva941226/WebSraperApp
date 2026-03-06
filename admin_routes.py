"""
Admin Panel Routes - User Management
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from models import db, User
from werkzeug.security import generate_password_hash
from functools import wraps

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
    
    # Create user
    new_user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        user_type=user_type,
        credits=credits,
        license_type='multi',  # Default to multi for admin-created users
        is_active=True,
        is_verified=True
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
    user_id = request.form.get('user_id', type=int)
    amount = request.form.get('amount', type=int)
    reason = request.form.get('reason', 'Admin adjustment')
    
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))
    
    # Create credit transaction record
    from models import CreditTransaction
    transaction = CreditTransaction(
        user_id=user.id,
        amount=amount,
        transaction_type='admin_adjustment',
        description=f'{reason} (by admin: {session.get("username")})',
        balance_after=user.credits + amount
    )
    
    user.credits += amount
    db.session.add(transaction)
    db.session.commit()
    
    # Update session if it's the current user
    if session.get('user_id') == user_id:
        session['credits'] = user.credits
    
    users = User.query.order_by(User.created_at.desc()).all()
    action = 'Added' if amount > 0 else 'Deducted'
    return render_template('admin.html', users=users, 
        message=f'{action} {abs(amount)} credits for {user.username}', message_type='success')


@admin_bp.route('/toggle-user/<int:user_id>')
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
    import json
    user_id = request.form.get('user_id', type=int)
    scrapers = request.form.getlist('scrapers')
    all_scrapers = request.form.get('all_scrapers') == 'on'
    
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))
    
    if all_scrapers or not scrapers:
        user.allowed_scrapers = 'all'
    else:
        user.allowed_scrapers = json.dumps(scrapers)
    
    db.session.commit()
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users, 
        message=f'Updated scraper permissions for {user.username}', message_type='success')


@admin_bp.route('/delete-user/<int:user_id>')
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
