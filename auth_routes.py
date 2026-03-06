"""
Authentication Routes - Login, Logout, Registration
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from models import db, User, _hash_password, _check_password
import hashlib
import platform

auth_bp = Blueprint('auth', __name__)


def get_machine_id():
    """Generate unique machine ID"""
    machine_info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
    return hashlib.sha256(machine_info.encode()).hexdigest()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler"""
    if request.method == 'GET':
        return render_template('login.html')
    
    username = request.form.get('username')
    password = request.form.get('password')
    remember = request.form.get('remember')
    
    if not username or not password:
        return render_template('login.html', error='Please provide username and password')
    
    # Find user by username or email
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()
    
    if not user:
        return render_template('login.html', error='Invalid username or password')
    
    if not _check_password(user.password_hash, password):
        return render_template('login.html', error='Invalid username or password')
    
    if not user.is_active:
        return render_template('login.html', error='Account is disabled. Contact administrator.')
    
    # Verify license for single-license users
    if user.license_type == 'single':
        current_machine = get_machine_id()
        
        if user.machine_id and user.machine_id != current_machine:
            return render_template('login.html', 
                error='License is registered to another machine. Contact administrator for multi-machine license.')
        
        # Register machine if first login
        if not user.machine_id:
            user.machine_id = current_machine
            db.session.commit()
    
    # Set session with all user data
    session['user_id'] = user.id
    session['username'] = user.username
    session['user_type'] = user.user_type
    session['credits'] = user.credits
    session['email'] = user.email
    session['allowed_scrapers'] = user.allowed_scrapers or 'all'
    session.permanent = bool(remember)
    
    # Update last login
    from datetime import datetime
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    return redirect(url_for('index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page and handler"""
    if request.method == 'GET':
        return render_template('register.html')
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    user_type = request.form.get('user_type', 'external')
    license_type = request.form.get('license_type', 'single')
    initial_credits = request.form.get('initial_credits', 100, type=int)
    
    # Validation
    if not all([username, email, password, confirm_password]):
        return render_template('register.html', error='All fields are required')
    
    if password != confirm_password:
        return render_template('register.html', error='Passwords do not match')
    
    if len(password) < 8:
        return render_template('register.html', error='Password must be at least 8 characters')
    
    # Check if username or email exists
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        return render_template('register.html', error='Username or email already exists')
    
    # Validate user type
    if user_type not in ['external', 'internal', 'admin']:
        user_type = 'external'
    
    # Create new user
    new_user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password),
        user_type=user_type,
        license_type=license_type,
        credits=initial_credits,
        is_active=True,
        is_verified=True  # Auto-verify for now
    )
    
    db.session.add(new_user)
    
    try:
        db.session.commit()
        return redirect(url_for('auth.login', success='Account created successfully! Please login.'))
    except Exception as e:
        db.session.rollback()
        return render_template('register.html', error=f'Registration failed: {str(e)}')


@auth_bp.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('index'))


@auth_bp.route('/profile')
def profile():
    """User profile page"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Get recent credit transactions
    from models import CreditTransaction
    transactions = CreditTransaction.query.filter_by(user_id=user.id).order_by(
        CreditTransaction.created_at.desc()
    ).limit(10).all()
    
    return render_template('profile.html', user=user, transactions=transactions)
