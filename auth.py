"""
Authentication and Authorization Module
Handles user login, registration, and access control
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request
from models import User, db
import hashlib
import platform
import uuid


def get_machine_id():
    """
    Generate a unique machine ID for license validation
    Uses a combination of hardware and OS identifiers
    """
    try:
        # Get machine identifiers
        machine_info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
        # Create hash for privacy
        machine_hash = hashlib.sha256(machine_info.encode()).hexdigest()
        return machine_hash
    except Exception as e:
        print(f"Error getting machine ID: {e}")
        return str(uuid.uuid4())


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.user_type != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def internal_user_required(f):
    """Decorator to require internal user access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.user_type not in ['admin', 'internal']:
            flash('Internal user access required.', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def validate_license(user):
    """
    Validate user license based on machine ID
    Returns (is_valid, error_message)
    """
    if user.user_type == 'admin':
        return True, None
    
    if user.license_type == 'single':
        current_machine_id = get_machine_id()
        
        # First time login - register machine
        if not user.machine_id:
            user.machine_id = current_machine_id
            db.session.commit()
            return True, None
        
        # Check if same machine
        if user.machine_id != current_machine_id:
            return False, "Single license can only be used on one machine. Contact admin for multi-license."
        
        return True, None
    
    elif user.license_type == 'multi':
        # Multi-license allows any machine
        return True, None
    
    return False, "Invalid license type."


def check_credits(user, required_credits):
    """
    Check if user has enough credits
    Returns (has_credits, error_message)
    """
    if user.user_type == 'admin':
        return True, None  # Admin has unlimited credits
    
    if user.credits < required_credits:
        return False, f"Insufficient credits. Required: {required_credits}, Available: {user.credits}"
    
    return True, None


def get_current_user():
    """Get the currently logged-in user"""
    if 'user_id' not in session:
        return None
    return User.query.get(session['user_id'])


def calculate_download_credits(record_count, file_format='csv'):
    """
    Calculate credits required for download based on record count
    Pricing: 1 credit per 100 records (minimum 1 credit)
    XLSX costs 20% more than CSV
    """
    base_credits = max(1, (record_count + 99) // 100)  # Round up
    
    if file_format == 'xlsx':
        return int(base_credits * 1.2)
    
    return base_credits
