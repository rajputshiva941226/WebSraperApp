"""
Credit System Routes
Handles credit management, transactions, and download tracking
"""

from flask import Blueprint, request, jsonify, render_template, session, send_file
from models import db, User, CreditTransaction, Download, MasterDatabase
from auth import login_required, admin_required, get_current_user, check_credits, calculate_download_credits
import os
import csv

credit_bp = Blueprint('credit', __name__)


@credit_bp.route('/api/credits/balance')
@login_required
def get_credit_balance():
    """Get current user's credit balance"""
    user = get_current_user()
    return jsonify({
        'credits': user.credits,
        'username': user.username,
        'user_type': user.user_type
    })


@credit_bp.route('/api/credits/transactions')
@login_required
def get_credit_transactions():
    """Get user's credit transaction history"""
    user = get_current_user()
    limit = request.args.get('limit', 50, type=int)
    
    transactions = CreditTransaction.query\
        .filter_by(user_id=user.id)\
        .order_by(CreditTransaction.created_at.desc())\
        .limit(limit)\
        .all()
    
    return jsonify({
        'transactions': [t.to_dict() for t in transactions],
        'current_balance': user.credits
    })


@credit_bp.route('/api/credits/add', methods=['POST'])
@admin_required
def add_credits():
    """Admin: Add credits to a user"""
    data = request.json
    
    user_id = data.get('user_id')
    amount = data.get('amount', 0)
    description = data.get('description', 'Admin credit addition')
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.add_credits(amount, description)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'new_balance': user.credits,
        'message': f'Added {amount} credits to {user.username}'
    })


@credit_bp.route('/api/download/<job_id>/check')
@login_required
def check_download_cost(job_id):
    """Check credits required for download"""
    user = get_current_user()
    file_format = request.args.get('format', 'csv')
    
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
    
    # Calculate cost
    record_count = job.get('unique_emails', 0)
    credits_required = calculate_download_credits(record_count, file_format)
    
    has_credits, error_msg = check_credits(user, credits_required)
    
    return jsonify({
        'job_id': job_id,
        'record_count': record_count,
        'file_format': file_format,
        'credits_required': credits_required,
        'user_credits': user.credits,
        'can_download': has_credits,
        'error': error_msg if not has_credits else None
    })


@credit_bp.route('/api/download/<job_id>/execute', methods=['POST'])
@login_required
def execute_download_with_credits(job_id):
    """Execute download and deduct credits"""
    user = get_current_user()
    data = request.json
    file_format = data.get('format', 'csv')
    
    # Import from app.py context
    from app import active_jobs, job_history, count_results_detailed
    
    # Find job
    job = active_jobs.get(job_id)
    if not job:
        for hist_job in job_history:
            if hist_job.get('id') == job_id:
                job = hist_job
                break
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job.get('status') not in ['completed', 'failed']:
        return jsonify({'error': 'Job not completed yet'}), 400
    
    # Get file path
    output_file = job.get('output_file')
    if not output_file or not os.path.exists(output_file):
        return jsonify({'error': 'Output file not found'}), 404
    
    # Count records
    total_records, emails_count, unique_authors, unique_emails, unique_links = count_results_detailed(output_file)
    
    # Calculate credits
    credits_required = calculate_download_credits(unique_emails, file_format)
    
    # Check credits (admin bypass)
    if user.user_type != 'admin':
        has_credits, error_msg = check_credits(user, credits_required)
        if not has_credits:
            return jsonify({'error': error_msg}), 403
        
        # Deduct credits
        if not user.deduct_credits(credits_required, f'Download: {job.get("journal_name")} - {job.get("keyword")}'):
            return jsonify({'error': 'Failed to deduct credits'}), 500
    
    # Create download record
    download = Download(
        user_id=user.id,
        job_id=job_id,
        file_format=file_format,
        file_path=output_file,
        total_records=total_records,
        unique_emails=unique_emails,
        credits_deducted=credits_required if user.user_type != 'admin' else 0,
        journal_name=job.get('journal_name'),
        keyword=job.get('keyword')
    )
    db.session.add(download)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'download_id': download.id,
        'credits_deducted': credits_required if user.user_type != 'admin' else 0,
        'remaining_credits': user.credits,
        'download_url': f'/api/download/{job_id}/file?format={file_format}&token={download.id}'
    })


@credit_bp.route('/api/credits/admin/users')
@admin_required
def admin_list_users():
    """Admin: List all users with credit info"""
    users = User.query.order_by(User.created_at.desc()).all()
    
    return jsonify({
        'users': [u.to_dict() for u in users]
    })


@credit_bp.route('/credits/manage')
@admin_required
def credit_management_page():
    """Admin page for managing user credits"""
    return render_template('admin/credits.html')


@credit_bp.route('/api/downloads/history')
@login_required
def download_history():
    """Get user's download history"""
    user = get_current_user()
    limit = request.args.get('limit', 50, type=int)
    
    downloads = Download.query\
        .filter_by(user_id=user.id)\
        .order_by(Download.downloaded_at.desc())\
        .limit(limit)\
        .all()
    
    return jsonify({
        'downloads': [d.to_dict() for d in downloads],
        'total_credits_spent': sum(d.credits_deducted for d in downloads)
    })


@credit_bp.route('/api/credits/stats')
@admin_required
def credit_stats():
    """Admin: Get credit system statistics"""
    total_users = User.query.count()
    total_credits_issued = db.session.query(db.func.sum(User.credits)).scalar() or 0
    total_downloads = Download.query.count()
    total_credits_spent = db.session.query(db.func.sum(Download.credits_deducted)).scalar() or 0
    
    # Recent transactions
    recent_transactions = CreditTransaction.query\
        .order_by(CreditTransaction.created_at.desc())\
        .limit(20)\
        .all()
    
    return jsonify({
        'total_users': total_users,
        'total_credits_issued': total_credits_issued,
        'total_downloads': total_downloads,
        'total_credits_spent': total_credits_spent,
        'recent_transactions': [t.to_dict() for t in recent_transactions]
    })
