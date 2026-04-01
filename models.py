"""
Database Models for Journal Scraper Application
Includes: Users, Credits, Master Database, and Download Tracking
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import uuid
from werkzeug.security import generate_password_hash, check_password_hash as _wz_check_password_hash
try:
    import bcrypt as _bcrypt
    _USE_BCRYPT = True
except ImportError:
    _USE_BCRYPT = False


def _hash_password(password):
    if _USE_BCRYPT:
        return _bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt(rounds=12)).decode('utf-8')
    return generate_password_hash(password, method='pbkdf2:sha256:260000')


def _check_password(password_hash, password):
    if not password_hash:
        return False
    # bcrypt hashes start with $2b$ or $2a$
    if _USE_BCRYPT and password_hash.startswith('$2'):
        try:
            return _bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    # Fallback: werkzeug pbkdf2/scrypt hashes (existing users)
    try:
        return _wz_check_password_hash(password_hash, password)
    except Exception:
        return False

db = SQLAlchemy()

class User(db.Model):
    """User model for authentication and authorization"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # User type: 'admin', 'internal', 'external'
    user_type = db.Column(db.String(20), nullable=False, default='external')
    
    # Credits for downloads
    credits = db.Column(db.Integer, nullable=False, default=0)
    
    # License information
    license_type = db.Column(db.String(50), default='single')  # 'single', 'multi'
    machine_id = db.Column(db.String(200), nullable=True, index=True)  # For single-machine licenses (not unique — PostgreSQL NULLs are distinct but causes ORM headaches)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    allowed_scrapers = db.Column(db.Text, default='all')  # JSON list of allowed scrapers or 'all'
    allowed_conferences = db.Column(db.Text, default='all')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    downloads = db.relationship('Download', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    credit_transactions = db.relationship('CreditTransaction', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set password using bcrypt"""
        self.password_hash = _hash_password(password)

    def check_password(self, password):
        """Verify password using bcrypt-aware check"""
        return _check_password(self.password_hash, password)

    def deduct_credits(self, amount, description):
        """Deduct credits and create transaction record"""
        if self.credits < amount:
            return False
        
        self.credits -= amount
        transaction = CreditTransaction(
            user_id=self.id,
            amount=-amount,
            transaction_type='deduction',
            description=description
        )
        db.session.add(transaction)
        return True
    
    def add_credits(self, amount, description):
        """Add credits and create transaction record"""
        self.credits += amount
        transaction = CreditTransaction(
            user_id=self.id,
            amount=amount,
            transaction_type='addition',
            description=description
        )
        db.session.add(transaction)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'user_type': self.user_type,
            'credits': self.credits,
            'license_type': self.license_type,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    def get_allowed_conferences(self):
        """
        Returns a list of allowed conference codes, or the string 'all'.
        Mirrors the pattern used by get_allowed_scrapers().
        """
        val = self.allowed_conferences or 'all'
        if val == 'all':
            return 'all'
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            return 'all'
 
    def can_access_conference(self, code: str) -> bool:
        """Returns True if this user may submit jobs for the given conference code."""
        allowed = self.get_allowed_conferences()
        return allowed == 'all' or code in allowed
 

class CreditTransaction(db.Model):
    """Track all credit transactions"""
    __tablename__ = 'credit_transactions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    
    amount = db.Column(db.Integer, nullable=False)  # Positive for addition, negative for deduction
    transaction_type = db.Column(db.String(20), nullable=False)  # 'addition', 'deduction', 'refund'
    description = db.Column(db.String(255))
    
    # Reference to job/download if applicable
    job_id = db.Column(db.String(36))
    download_id = db.Column(db.String(36), db.ForeignKey('downloads.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'amount': self.amount,
            'transaction_type': self.transaction_type,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Download(db.Model):
    """Track all downloads with credit deduction"""
    __tablename__ = 'downloads'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    
    # Job and file information
    job_id = db.Column(db.String(36), nullable=False)
    file_format = db.Column(db.String(10))  # 'csv' or 'xlsx'
    file_path = db.Column(db.String(500))
    
    # Record counts
    total_records = db.Column(db.Integer, default=0)
    unique_emails = db.Column(db.Integer, default=0)
    
    # Credits
    credits_deducted = db.Column(db.Integer, default=0)
    
    # Metadata
    journal_name = db.Column(db.String(100))
    keyword = db.Column(db.String(255))
    
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'job_id': self.job_id,
            'file_format': self.file_format,
            'total_records': self.total_records,
            'unique_emails': self.unique_emails,
            'credits_deducted': self.credits_deducted,
            'journal_name': self.journal_name,
            'keyword': self.keyword,
            'downloaded_at': self.downloaded_at.isoformat() if self.downloaded_at else None
        }


class MasterDatabase(db.Model):
    """
    Master database for storing all unique author-email combinations
    Deduplication based on email
    """
    __tablename__ = 'master_database'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Author information
    author_name = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    affiliation = db.Column(db.Text)
    
    # Source information
    conference_name = db.Column(db.String(255), index=True)
    conference_code = db.Column(db.String(30),  default='', index=True)
    journal_name = db.Column(db.String(100), index=True)
    article_title = db.Column(db.Text)
    article_url = db.Column(db.Text)
    
    # Metadata
    keyword = db.Column(db.String(255), index=True)
    scraped_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Job reference
    job_id = db.Column(db.String(36))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=lambda: datetime.utcnow())
    
    def to_dict(self):
        return {
            'id': self.id,
            'author_name': self.author_name,
            'email': self.email,
            'affiliation': self.affiliation,
            'conference_name': self.conference_name,
            'journal_name': self.journal_name,
            'article_title': self.article_title,
            'article_url': self.article_url,
            'keyword': self.keyword,
            'scraped_date': self.scraped_date.isoformat() if self.scraped_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ConferenceMaster(db.Model):
    """
    Master data for conferences uploaded by internal users
    """
    __tablename__ = 'conference_master'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Conference information
    conference_name = db.Column(db.String(255), nullable=False, index=True)
    conference_year = db.Column(db.Integer)
    conference_location = db.Column(db.String(255))
    
    # Author information
    author_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    affiliation = db.Column(db.Text)
    
    # Upload metadata
    uploaded_by = db.Column(db.String(36), db.ForeignKey('users.id'))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    source_file = db.Column(db.String(500))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Composite unique constraint on conference + email
    __table_args__ = (
        db.UniqueConstraint('conference_name', 'email', name='unique_conference_email'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'conference_name': self.conference_name,
            'conference_year': self.conference_year,
            'author_name': self.author_name,
            'email': self.email,
            'affiliation': self.affiliation,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None
        }


class Job(db.Model):
    """
    Track scraping jobs
    """
    __tablename__ = 'job'
    
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    
    # Job parameters
    journal = db.Column(db.String(50), index=True)
    journal_name = db.Column(db.String(255))
    keyword = db.Column(db.String(255), index=True)
    conference = db.Column(db.String(255))
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    mesh_type = db.Column(db.String(50))
    
    # Job status
    status = db.Column(db.String(20), default='pending', index=True)  # pending, running, completed, failed
    progress = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    error = db.Column(db.Text)
    
    # Job results
    output_file = db.Column(db.String(500))
    authors_count = db.Column(db.Integer, default=0)
    emails_count = db.Column(db.Integer, default=0)
    unique_authors = db.Column(db.Integer, default=0)
    unique_emails = db.Column(db.Integer, default=0)
    unique_links = db.Column(db.Integer, default=0)
    
    # Current scraping state
    current_url = db.Column(db.String(500))
    links_count = db.Column(db.Integer, default=0)
    
    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Float)
    
    # Flags
    has_partial_results = db.Column(db.Boolean, default=False)
    stop_requested = db.Column(db.Boolean, default=False)

    # Worker tracking
    worker_task_id = db.Column(db.String(36))
    last_heartbeat_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'journal': self.journal,
            'journal_name': self.journal_name,
            'keyword': self.keyword,
            'conference': self.conference,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'mesh_type': self.mesh_type,
            'status': self.status,
            'progress': self.progress,
            'message': self.message,
            'error': self.error,
            'output_file': self.output_file,
            'authors_count': self.authors_count,
            'emails_count': self.emails_count,
            'unique_authors': self.unique_authors,
            'unique_emails': self.unique_emails,
            'unique_links': self.unique_links,
            'current_url': self.current_url,
            'links_count': self.links_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'has_partial_results': self.has_partial_results,
            'stop_requested': self.stop_requested,
            'worker_task_id': self.worker_task_id,
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None
        }


class SearchHistory(db.Model):
    """
    Track search history for 7-day retention
    """
    __tablename__ = 'search_history'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    
    # Search parameters
    keyword = db.Column(db.String(255), index=True)
    conference_name = db.Column(db.String(255))
    journals = db.Column(db.Text)  # JSON array of journals
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    
    # Results summary
    total_results = db.Column(db.Integer, default=0)
    job_id = db.Column(db.String(36))
    
    # Timestamps
    searched_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        import json
        return {
            'id': self.id,
            'keyword': self.keyword,
            'conference_name': self.conference_name,
            'journals': json.loads(self.journals) if self.journals else [],
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_results': self.total_results,
            'searched_at': self.searched_at.isoformat() if self.searched_at else None
        }

class Conference(db.Model):
    """
    Stores conference definitions (code + display name).
    Seeded from CONFERENCES dict in conferences_config.py;
    admins can also create new ones at runtime via the admin panel.
    """
    __tablename__ = 'conferences'
 
    id           = db.Column(db.Integer, primary_key=True)
    code         = db.Column(db.String(30), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(200), nullable=False)
    is_active    = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    created_by   = db.Column(db.String(100), default='system')   # 'system' or admin username
 
    def to_dict(self):
        return {
            'id':           self.id,
            'code':         self.code,
            'display_name': self.display_name,
            'is_active':    self.is_active,
            'created_at':   self.created_at.isoformat() if self.created_at else None,
            'created_by':   self.created_by,
        }
# Utility functions

def init_db(app):
    """Initialize database with app"""
    db.init_app(app)
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created/verified successfully")
        except Exception as e:
            print(f"[DB] Warning during create_all: {e}")


def create_admin_user(username, email, password):
    """Create an admin user"""
    admin = User(
        username=username,
        email=email,
        user_type='admin',
        license_type='multi',
        machine_id=None,
        credits=999999,  # Admin gets unlimited credits
        is_active=True,
        is_verified=True
    )
    admin.password_hash = _hash_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin


def cleanup_old_search_history(days=7):
    """Delete search history older than specified days"""
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    deleted = SearchHistory.query.filter(SearchHistory.searched_at < cutoff_date).delete()
    db.session.commit()
    return deleted
