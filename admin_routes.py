# """
# Admin Panel Routes - User Management
# """

# from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
# from models import db, User, _hash_password
# from functools import wraps
# import json as _json

# admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# def admin_required(f):
#     """Decorator to require admin access"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'user_id' not in session:
#             return redirect(url_for('auth.login'))
        
#         if session.get('user_type') != 'admin':
#             return "Access Denied: Admin privileges required", 403
        
#         return f(*args, **kwargs)
#     return decorated_function


# @admin_bp.route('/')
# @admin_required
# def admin_panel():
#     """Admin dashboard with user management"""
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users)


# @admin_bp.route('/create-user', methods=['POST'])
# @admin_required
# def create_user():
#     """Create a new user"""
#     username = request.form.get('username')
#     email = request.form.get('email')
#     password = request.form.get('password')
#     user_type = request.form.get('user_type', 'external')
#     credits = request.form.get('credits', 100, type=int)
    
#     # Check if user exists
#     existing = User.query.filter(
#         (User.username == username) | (User.email == email)
#     ).first()
    
#     if existing:
#         users = User.query.order_by(User.created_at.desc()).all()
#         return render_template('admin.html', users=users, 
#             message='Username or email already exists', message_type='error')
    
#     # Get allowed scrapers
#     import json
#     scrapers = request.form.getlist('scrapers')
#     all_scrapers = request.form.get('all_scrapers') == 'on'
#     if all_scrapers or not scrapers:
#         allowed_scrapers = 'all'
#     else:
#         allowed_scrapers = json.dumps(scrapers)

#     license_type = request.form.get('license_type', 'multi')
#     if license_type not in ('single', 'multi'):
#         license_type = 'multi'

#     # Create user
#     new_user = User(
#         username=username,
#         email=email,
#         password_hash=_hash_password(password),
#         user_type=user_type,
#         credits=credits,
#         license_type=license_type,
#         is_active=True,
#         is_verified=True,
#         allowed_scrapers=allowed_scrapers
#     )
    
#     db.session.add(new_user)
#     db.session.commit()
    
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users, 
#         message=f'User {username} created successfully!', message_type='success')


# @admin_bp.route('/add-credits', methods=['POST'])
# @admin_required
# def add_credits():
#     """Add or deduct credits from a user with transaction logging"""
#     user_id = request.form.get('user_id') or (request.json or {}).get('user_id')
#     amount_raw = request.form.get('amount') or (request.json or {}).get('amount')
#     reason = request.form.get('reason') or (request.json or {}).get('reason', 'Admin adjustment')

#     try:
#         amount = int(amount_raw)
#     except (TypeError, ValueError):
#         return jsonify({'error': 'Invalid amount'}), 400

#     user = User.query.get(user_id)
#     if not user:
#         return jsonify({'error': 'User not found'}), 404

#     from models import CreditTransaction
#     transaction = CreditTransaction(
#         user_id=user.id,
#         amount=amount,
#         transaction_type='admin_adjustment',
#         description=f'{reason} (by admin: {session.get("username")})'
#     )
#     user.credits += amount
#     db.session.add(transaction)
#     db.session.commit()

#     if session.get('user_id') == user_id:
#         session['credits'] = user.credits

#     action = 'Added' if amount > 0 else 'Deducted'
#     if request.is_json:
#         return jsonify({'success': True, 'message': f'{action} {abs(amount)} credits for {user.username}', 'new_credits': user.credits})
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users,
#         message=f'{action} {abs(amount)} credits for {user.username}', message_type='success')


# @admin_bp.route('/toggle-user/<user_id>')
# @admin_required
# def toggle_user(user_id):
#     """Enable or disable a user"""
#     user = User.query.get(user_id)
#     if not user:
#         return redirect(url_for('admin.admin_panel'))
    
#     # Prevent disabling the last admin
#     if user.user_type == 'admin' and user.is_active:
#         admin_count = User.query.filter_by(user_type='admin', is_active=True).count()
#         if admin_count <= 1:
#             users = User.query.order_by(User.created_at.desc()).all()
#             return render_template('admin.html', users=users, 
#                 message='Cannot disable the last active admin', message_type='error')
    
#     user.is_active = not user.is_active
#     db.session.commit()
    
#     # Log out user if they're being disabled and currently logged in
#     if not user.is_active and session.get('user_id') == user_id:
#         session.clear()
#         return redirect(url_for('auth.login'))
    
#     users = User.query.order_by(User.created_at.desc()).all()
#     status = 'enabled' if user.is_active else 'disabled'
#     return render_template('admin.html', users=users, 
#         message=f'User {user.username} {status}', message_type='success')


# @admin_bp.route('/manage-scrapers', methods=['POST'])
# @admin_required
# def manage_scrapers():
#     """Update user's allowed scrapers"""
#     if request.is_json:
#         data = request.json
#         user_id = data.get('user_id')
#         scrapers = data.get('scrapers', [])
#         all_scrapers = data.get('all_scrapers', False)
#     else:
#         user_id = request.form.get('user_id')
#         scrapers = request.form.getlist('scrapers')
#         all_scrapers = request.form.get('all_scrapers') == 'on'

#     user = User.query.get(user_id)
#     if not user:
#         if request.is_json:
#             return jsonify({'error': 'User not found'}), 404
#         return redirect(url_for('admin.admin_panel'))

#     user.allowed_scrapers = 'all' if (all_scrapers or not scrapers) else _json.dumps(scrapers)
#     db.session.commit()

#     if request.is_json:
#         return jsonify({'success': True, 'message': f'Updated scraper permissions for {user.username}'})
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users,
#         message=f'Updated scraper permissions for {user.username}', message_type='success')


# @admin_bp.route('/edit-user', methods=['POST'])
# @admin_required
# def edit_user():
#     """Edit user details: username, email, password, user_type, license_type, credits"""
#     if request.is_json:
#         data = request.json
#     else:
#         data = request.form

#     user_id = data.get('user_id')
#     user = User.query.get(user_id)
#     if not user:
#         if request.is_json:
#             return jsonify({'error': 'User not found'}), 404
#         return redirect(url_for('admin.admin_panel'))

#     new_username = data.get('username', '').strip()
#     new_email = data.get('email', '').strip()
#     new_password = data.get('password', '').strip()
#     new_user_type = data.get('user_type', user.user_type)
#     new_license_type = data.get('license_type', user.license_type)
#     new_credits = data.get('credits')

#     # Validate uniqueness
#     if new_username and new_username != user.username:
#         if User.query.filter(User.username == new_username, User.id != user_id).first():
#             if request.is_json:
#                 return jsonify({'error': 'Username already taken'}), 400
#             users = User.query.order_by(User.created_at.desc()).all()
#             return render_template('admin.html', users=users, message='Username already taken', message_type='error')
#         user.username = new_username

#     if new_email and new_email != user.email:
#         if User.query.filter(User.email == new_email, User.id != user_id).first():
#             if request.is_json:
#                 return jsonify({'error': 'Email already taken'}), 400
#             users = User.query.order_by(User.created_at.desc()).all()
#             return render_template('admin.html', users=users, message='Email already taken', message_type='error')
#         user.email = new_email

#     if new_password and len(new_password) >= 8:
#         user.password_hash = _hash_password(new_password)

#     if new_user_type in ('admin', 'internal', 'external'):
#         user.user_type = new_user_type

#     if new_license_type in ('single', 'multi'):
#         user.license_type = new_license_type
#         if new_license_type == 'multi':
#             user.machine_id = None  # Clear machine lock for multi-license

#     if new_credits is not None:
#         try:
#             user.credits = int(new_credits)
#         except (TypeError, ValueError):
#             pass

#     db.session.commit()

#     # Update session if editing self
#     if session.get('user_id') == user_id:
#         session['username'] = user.username
#         session['user_type'] = user.user_type
#         session['credits'] = user.credits
#         session['email'] = user.email

#     if request.is_json:
#         return jsonify({'success': True, 'message': f'User {user.username} updated successfully'})
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users,
#         message=f'User {user.username} updated successfully', message_type='success')


# @admin_bp.route('/delete-user/<user_id>')
# @admin_required
# def delete_user(user_id):
#     """Delete a user (soft delete or hard delete)"""
#     user = User.query.get(user_id)
#     if not user:
#         return redirect(url_for('admin.admin_panel'))
    
#     # Prevent deleting the last admin
#     if user.user_type == 'admin':
#         admin_count = User.query.filter_by(user_type='admin').count()
#         if admin_count <= 1:
#             users = User.query.order_by(User.created_at.desc()).all()
#             return render_template('admin.html', users=users, 
#                 message='Cannot delete the last admin', message_type='error')
    
#     username = user.username
#     db.session.delete(user)
#     db.session.commit()
    
#     users = User.query.order_by(User.created_at.desc()).all()
#     return render_template('admin.html', users=users, 
#         message=f'User {username} deleted', message_type='success')


"""
Admin Panel Routes — User Management + Conference Management
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from models import db, User, _hash_password
from functools import wraps
import json as _json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ═══════════════════════════════════════════════════════════════════
# Auth decorator
# ═══════════════════════════════════════════════════════════════════

def admin_required(f):
    """Decorator to require admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('user_type') != 'admin':
            return "Access Denied: Admin privileges required", 403
        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _all_conferences():
    """Return all Conference rows ordered by display_name."""
    from models import Conference
    return Conference.query.order_by(Conference.display_name).all()


def _render_admin(message=None, message_type=None):
    """Render admin.html with current users and conferences."""
    users = User.query.order_by(User.created_at.desc()).all()
    conferences = _all_conferences()
    return render_template(
        'admin.html',
        users=users,
        conferences=conferences,
        message=message,
        message_type=message_type,
    )


# ═══════════════════════════════════════════════════════════════════
# Existing user-management routes (unchanged)
# ═══════════════════════════════════════════════════════════════════

@admin_bp.route('/')
@admin_required
def admin_panel():
    """Admin dashboard — user management + conference management."""
    return _render_admin()


@admin_bp.route('/create-user', methods=['POST'])
@admin_required
def create_user():
    """Create a new user."""
    username  = request.form.get('username')
    email     = request.form.get('email')
    password  = request.form.get('password')
    user_type = request.form.get('user_type', 'external')
    credits   = request.form.get('credits', 100, type=int)

    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        return _render_admin('Username or email already exists', 'error')

    import json
    scrapers     = request.form.getlist('scrapers')
    all_scrapers = request.form.get('all_scrapers') == 'on'
    allowed_scrapers = 'all' if (all_scrapers or not scrapers) else json.dumps(scrapers)

    conferences     = request.form.getlist('conferences')
    all_conferences = request.form.get('all_conferences') == 'on'
    allowed_conferences = 'all' if (all_conferences or not conferences) else json.dumps(conferences)

    license_type = request.form.get('license_type', 'multi')
    if license_type not in ('single', 'multi'):
        license_type = 'multi'

    new_user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password),
        user_type=user_type,
        credits=credits,
        license_type=license_type,
        is_active=True,
        is_verified=True,
        allowed_scrapers=allowed_scrapers,
        allowed_conferences=allowed_conferences,
    )
    db.session.add(new_user)
    db.session.commit()

    return _render_admin(f'User {username} created successfully!', 'success')


@admin_bp.route('/add-credits', methods=['POST'])
@admin_required
def add_credits():
    """Add or deduct credits from a user with transaction logging."""
    user_id    = request.form.get('user_id')    or (request.json or {}).get('user_id')
    amount_raw = request.form.get('amount')     or (request.json or {}).get('amount')
    reason     = request.form.get('reason')     or (request.json or {}).get('reason', 'Admin adjustment')

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
        return jsonify({
            'success': True,
            'message': f'{action} {abs(amount)} credits for {user.username}',
            'new_credits': user.credits,
        })
    return _render_admin(f'{action} {abs(amount)} credits for {user.username}', 'success')


@admin_bp.route('/toggle-user/<user_id>')
@admin_required
def toggle_user(user_id):
    """Enable or disable a user."""
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))

    if user.user_type == 'admin' and user.is_active:
        admin_count = User.query.filter_by(user_type='admin', is_active=True).count()
        if admin_count <= 1:
            return _render_admin('Cannot disable the last active admin', 'error')

    user.is_active = not user.is_active
    db.session.commit()

    if not user.is_active and session.get('user_id') == user_id:
        session.clear()
        return redirect(url_for('auth.login'))

    status = 'enabled' if user.is_active else 'disabled'
    return _render_admin(f'User {user.username} {status}', 'success')


@admin_bp.route('/manage-scrapers', methods=['POST'])
@admin_required
def manage_scrapers():
    """Update user's allowed scrapers."""
    if request.is_json:
        data        = request.json
        user_id     = data.get('user_id')
        scrapers    = data.get('scrapers', [])
        all_scrapers = data.get('all_scrapers', False)
    else:
        user_id     = request.form.get('user_id')
        scrapers    = request.form.getlist('scrapers')
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
    return _render_admin(f'Updated scraper permissions for {user.username}', 'success')


@admin_bp.route('/edit-user', methods=['POST'])
@admin_required
def edit_user():
    """Edit user details: username, email, password, user_type, license_type, credits."""
    data    = request.json if request.is_json else request.form
    user_id = data.get('user_id')
    user    = User.query.get(user_id)

    if not user:
        if request.is_json:
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('admin.admin_panel'))

    new_username     = data.get('username', '').strip()
    new_email        = data.get('email', '').strip()
    new_password     = data.get('password', '').strip()
    new_user_type    = data.get('user_type', user.user_type)
    new_license_type = data.get('license_type', user.license_type)
    new_credits      = data.get('credits')

    if new_username and new_username != user.username:
        if User.query.filter(User.username == new_username, User.id != user_id).first():
            if request.is_json:
                return jsonify({'error': 'Username already taken'}), 400
            return _render_admin('Username already taken', 'error')
        user.username = new_username

    if new_email and new_email != user.email:
        if User.query.filter(User.email == new_email, User.id != user_id).first():
            if request.is_json:
                return jsonify({'error': 'Email already taken'}), 400
            return _render_admin('Email already taken', 'error')
        user.email = new_email

    if new_password and len(new_password) >= 8:
        user.password_hash = _hash_password(new_password)

    if new_user_type in ('admin', 'internal', 'external'):
        user.user_type = new_user_type

    if new_license_type in ('single', 'multi'):
        user.license_type = new_license_type
        if new_license_type == 'multi':
            user.machine_id = None

    if new_credits is not None:
        try:
            user.credits = int(new_credits)
        except (TypeError, ValueError):
            pass

    db.session.commit()

    if session.get('user_id') == user_id:
        session['username']  = user.username
        session['user_type'] = user.user_type
        session['credits']   = user.credits
        session['email']     = user.email

    if request.is_json:
        return jsonify({'success': True, 'message': f'User {user.username} updated successfully'})
    return _render_admin(f'User {user.username} updated successfully', 'success')


@admin_bp.route('/delete-user/<user_id>')
@admin_required
def delete_user(user_id):
    """Delete a user."""
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for('admin.admin_panel'))

    if user.user_type == 'admin':
        admin_count = User.query.filter_by(user_type='admin').count()
        if admin_count <= 1:
            return _render_admin('Cannot delete the last admin', 'error')

    username = user.username
    db.session.delete(user)
    db.session.commit()
    return _render_admin(f'User {username} deleted', 'success')


# ═══════════════════════════════════════════════════════════════════
# NEW: Conference management routes
# ═══════════════════════════════════════════════════════════════════

@admin_bp.route('/conferences')
@admin_required
def list_conferences():
    """
    JSON list of all conferences — used by admin UI to populate dropdowns.
    Returns both active and inactive so the admin can manage all of them.
    """
    from models import Conference
    rows = Conference.query.order_by(Conference.display_name).all()
    return jsonify({'conferences': [r.to_dict() for r in rows]})


@admin_bp.route('/conferences/create', methods=['POST'])
@admin_required
def create_conference():
    """
    Create a new conference definition.
    Accepts JSON or form-encoded body.
    Body: { code, display_name }
    Code is auto-uppercased and stripped of spaces.
    """
    from models import Conference
    data = request.json if request.is_json else request.form

    raw_code     = (data.get('code') or '').strip().upper().replace(' ', '_')
    display_name = (data.get('display_name') or '').strip()

    if not raw_code or not display_name:
        err = 'Both code and display_name are required'
        if request.is_json:
            return jsonify({'error': err}), 400
        return _render_admin(err, 'error')

    if len(raw_code) > 30:
        err = 'Conference code must be 30 characters or fewer'
        if request.is_json:
            return jsonify({'error': err}), 400
        return _render_admin(err, 'error')

    if Conference.query.filter_by(code=raw_code).first():
        err = f'Conference code "{raw_code}" already exists'
        if request.is_json:
            return jsonify({'error': err}), 400
        return _render_admin(err, 'error')

    conf = Conference(
        code=raw_code,
        display_name=display_name,
        is_active=True,
        created_by=session.get('username', 'admin'),
    )
    db.session.add(conf)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'conference': conf.to_dict()})
    return _render_admin(f'Conference "{display_name}" ({raw_code}) created', 'success')


@admin_bp.route('/conferences/toggle/<string:code>', methods=['POST', 'GET'])
@admin_required
def toggle_conference(code):
    """
    Toggle a conference active/inactive.
    Inactive conferences are hidden from user dropdowns but preserved in the DB.
    """
    from models import Conference
    conf = Conference.query.filter_by(code=code.upper()).first()

    if not conf:
        if request.is_json:
            return jsonify({'error': 'Conference not found'}), 404
        return _render_admin(f'Conference "{code}" not found', 'error')

    conf.is_active = not conf.is_active
    db.session.commit()

    status = 'activated' if conf.is_active else 'deactivated'
    if request.is_json:
        return jsonify({
            'success': True,
            'message': f'Conference {conf.code} {status}',
            'is_active': conf.is_active,
        })
    return _render_admin(f'Conference "{conf.display_name}" {status}', 'success')


@admin_bp.route('/conferences/edit', methods=['POST'])
@admin_required
def edit_conference():
    """
    Edit a conference's display name (code is immutable once created).
    Body: { code, display_name }
    """
    from models import Conference
    data         = request.json if request.is_json else request.form
    code         = (data.get('code') or '').strip().upper()
    display_name = (data.get('display_name') or '').strip()

    if not code or not display_name:
        err = 'code and display_name are both required'
        return (jsonify({'error': err}), 400) if request.is_json else _render_admin(err, 'error')

    conf = Conference.query.filter_by(code=code).first()
    if not conf:
        err = f'Conference "{code}" not found'
        return (jsonify({'error': err}), 404) if request.is_json else _render_admin(err, 'error')

    conf.display_name = display_name
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'conference': conf.to_dict()})
    return _render_admin(f'Conference "{code}" updated', 'success')


@admin_bp.route('/conferences/delete/<string:code>', methods=['POST'])
@admin_required
def delete_conference(code):
    """Permanently delete a conference record."""
    from models import Conference
    conf = Conference.query.filter_by(code=code.upper()).first()
    if not conf:
        return jsonify({'success': False, 'error': 'Conference not found'}), 404
    display_name = conf.display_name
    db.session.delete(conf)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Conference "{display_name}" deleted'})


@admin_bp.route('/manage-conferences', methods=['POST'])
@admin_required
def manage_conferences():
    """
    Update a user's allowed conferences.
    Mirrors the manage-scrapers pattern exactly.

    Body: { user_id, conferences: [...codes], all_conferences: bool }
    """
    if request.is_json:
        data            = request.json
        user_id         = data.get('user_id')
        conferences     = data.get('conferences', [])
        all_conferences = data.get('all_conferences', False)
    else:
        user_id         = request.form.get('user_id')
        conferences     = request.form.getlist('conferences')
        all_conferences = request.form.get('all_conferences') == 'on'

    user = User.query.get(user_id)
    if not user:
        if request.is_json:
            return jsonify({'error': 'User not found'}), 404
        return redirect(url_for('admin.admin_panel'))

    user.allowed_conferences = (
        'all' if (all_conferences or not conferences)
        else _json.dumps(list(conferences))
    )
    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'message': f'Updated conference permissions for {user.username}',
            'allowed_conferences': user.allowed_conferences,
        })
    return _render_admin(f'Updated conference permissions for {user.username}', 'success')


@admin_bp.route('/api/user-conferences/<user_id>')
@admin_required
def get_user_conferences(user_id):
    """
    Return the conference access info for one user.
    Used by the admin panel JS to populate the conference permission editor.

    Response shape:
    {
      "allowed": "all" | ["NWC", "CGC", ...],
      "all_conferences": [ {code, display_name, is_active}, ... ]
    }
    """
    from models import Conference
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    allowed_raw = user.allowed_conferences or 'all'
    if allowed_raw == 'all':
        allowed = 'all'
    else:
        try:
            allowed = _json.loads(allowed_raw)
        except (ValueError, TypeError):
            allowed = 'all'

    all_confs = Conference.query.order_by(Conference.display_name).all()

    return jsonify({
        'allowed': allowed,
        'all_conferences': [
            {
                'code':         c.code,
                'display_name': c.display_name,
                'is_active':    c.is_active,
                'permitted':    (allowed == 'all' or c.code in allowed),
            }
            for c in all_confs
        ],
    })


# ═══════════════════════════════════════════════════════════════════
# NEW: Conferences dropdown endpoint (for user-facing forms)
# ═══════════════════════════════════════════════════════════════════

@admin_bp.route('/api/conferences-for-user')
def conferences_for_user():
    """
    Public (session-auth) endpoint: returns conferences the current logged-in
    user is allowed to select when submitting a scrape job.

    Returns: [ {code, display_name}, ... ] sorted by display_name.
    """
    from models import Conference

    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    allowed_raw = user.allowed_conferences or 'all'
    all_active  = Conference.query.filter_by(is_active=True)\
                                  .order_by(Conference.display_name)\
                                  .all()

    if allowed_raw == 'all':
        rows = all_active
    else:
        try:
            allowed_codes = set(_json.loads(allowed_raw))
        except (ValueError, TypeError):
            allowed_codes = set()
        rows = [c for c in all_active if c.code in allowed_codes]

    return jsonify({
        'conferences': [
            {'code': c.code, 'display_name': c.display_name}
            for c in rows
        ]
    })

