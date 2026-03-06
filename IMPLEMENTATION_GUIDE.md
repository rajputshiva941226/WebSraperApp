# Credit System & Master Database - Implementation Guide

## Overview
This guide covers the complete implementation of the credit system and master database features for the Journal Scraper application.

---

## 🎯 Features Implemented

### 1. Credit System
- **User Credits**: Token-based download system
- **Credit Transactions**: Complete audit trail of all credit activities
- **Download Tracking**: Track all downloads with credit deduction
- **Admin Controls**: Manage user credits, view statistics
- **Cost Calculation**: 1 credit per 100 records (XLSX costs 20% more)

### 2. Master Database
- **Centralized Storage**: All scraped data in one database
- **Email Deduplication**: Unique records based on email
- **Conference Master Data**: Upload and manage conference attendee data
- **Auto-Append**: Automatically add scraped results to master DB
- **Admin Download**: Only admin can export entire master database
- **Search & Filter**: Advanced search across all records

### 3. User Management
- **Authentication**: Login/logout system
- **User Types**: Admin, Internal, External
- **License Validation**: Single/Multi license support with machine ID tracking
- **Access Control**: Role-based permissions

---

## 📁 Files Created

### Database & Models
- `models.py` - SQLAlchemy models for all tables
  - User
  - CreditTransaction
  - Download
  - MasterDatabase
  - ConferenceMaster
  - SearchHistory

### Authentication
- `auth.py` - Authentication decorators and license validation
  - `@login_required`
  - `@admin_required`
  - `@internal_user_required`
  - License validation functions
  - Credit checking functions

### Routes
- `credit_routes.py` - Credit system API endpoints
- `master_db_routes.py` - Master database API endpoints

### Templates (To Be Created)
- `templates/login.html`
- `templates/register.html`
- `templates/master_database.html`
- `templates/admin/credits.html`
- `templates/admin/users.html`

---

## 🗄️ Database Schema

### Users Table
```sql
- id (UUID, PK)
- username (Unique)
- email (Unique)
- password_hash
- user_type (admin/internal/external)
- credits (Integer)
- license_type (single/multi)
- machine_id (For license validation)
- is_active, is_verified
- created_at, last_login
```

### Credit Transactions Table
```sql
- id (UUID, PK)
- user_id (FK → users)
- amount (+/-)
- transaction_type (addition/deduction/refund)
- description
- job_id, download_id
- created_at
```

### Downloads Table
```sql
- id (UUID, PK)
- user_id (FK → users)
- job_id
- file_format (csv/xlsx)
- total_records, unique_emails
- credits_deducted
- journal_name, keyword
- downloaded_at
```

### Master Database Table
```sql
- id (UUID, PK)
- author_name
- email (Unique)
- affiliation
- conference_name, journal_name
- article_title, article_url
- keyword, scraped_date
- job_id
- created_at, updated_at
```

### Conference Master Table
```sql
- id (UUID, PK)
- conference_name, conference_year
- author_name, email
- affiliation
- uploaded_by (FK → users)
- upload_date, source_file
- UNIQUE(conference_name, email)
```

### Search History Table
```sql
- id (UUID, PK)
- user_id (FK → users)
- keyword, conference_name
- journals (JSON)
- start_date, end_date
- total_results, job_id
- searched_at (Auto-cleanup after 7 days)
```

---

## 🔧 Integration Steps

### Step 1: Install Dependencies
```bash
pip install flask-sqlalchemy flask-login werkzeug pandas openpyxl
```

### Step 2: Update app.py
Add at the top:
```python
from flask import Flask, session
from models import db, init_db, create_admin_user, cleanup_old_search_history
from credit_routes import credit_bp
from master_db_routes import master_db_bp
import os

# Configure app
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///journal_scraper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
init_db(app)

# Register blueprints
app.register_blueprint(credit_bp)
app.register_blueprint(master_db_bp)
```

### Step 3: Initialize Database
```python
# Run once to create tables
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Create admin user
python -c "from app import app; from models import create_admin_user; app.app_context().push(); create_admin_user('admin', 'admin@example.com', 'admin123')"
```

### Step 4: Add Authentication to Download Endpoint
Replace current `/api/download/<job_id>` with credit-enabled version:
```python
@app.route('/api/download/<job_id>')
@login_required
def download_results(job_id):
    # Redirect to credit check endpoint
    return redirect(url_for('credit.check_download_cost', job_id=job_id))
```

---

## 📊 API Endpoints

### Credit System
```
GET  /api/credits/balance                    - Get user's credit balance
GET  /api/credits/transactions               - Get credit history
POST /api/credits/add                        - Admin: Add credits to user
GET  /api/download/<job_id>/check            - Check download cost
POST /api/download/<job_id>/execute          - Execute download with credit deduction
GET  /api/downloads/history                  - Get download history
GET  /api/credits/stats                      - Admin: Credit statistics
GET  /api/credits/admin/users                - Admin: List all users
```

### Master Database
```
GET  /master-database                        - Master DB management page
POST /api/master-database/upload             - Upload conference data (CSV/XLSX)
POST /api/master-database/append-scraped     - Auto-append scraped results
GET  /api/master-database/search             - Search master database
GET  /api/master-database/download           - Admin: Download entire master DB
GET  /api/master-database/stats              - Get statistics
GET  /api/conference-master/list             - List conference master data
```

---

## 💳 Credit Pricing

### Default Pricing Model
- **Base**: 1 credit per 100 records
- **Minimum**: 1 credit (even for <100 records)
- **XLSX Premium**: 20% more expensive than CSV
- **Admin**: Unlimited credits (bypass)

### Examples
- 50 records (CSV): 1 credit
- 150 records (CSV): 2 credits
- 500 records (CSV): 5 credits
- 500 records (XLSX): 6 credits
- Admin downloads: 0 credits (free)

---

## 👥 User Types & Permissions

### External Users
- **Required Fields**: Keyword only
- **Access**: Basic scraping, limited downloads
- **Credits**: Must have credits to download
- **Master DB**: No access

### Internal Users
- **Required Fields**: Keyword + Conference Name
- **Access**: Full scraping, master DB upload
- **Credits**: Must have credits to download
- **Master DB**: Can upload, search, auto-append

### Admin Users
- **Access**: Full system access
- **Credits**: Unlimited (no deduction)
- **Master DB**: Can download entire database
- **User Management**: Add/remove credits, manage users

---

## 🔐 License Validation

### Single License
- Tied to one machine via hardware ID
- First login registers machine
- Subsequent logins must match machine ID
- Prevents license sharing

### Multi License
- Can be used on any machine
- No machine ID restriction
- Higher cost tier

### Machine ID Generation
```python
# Uses: hostname + machine type + processor
machine_info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
machine_hash = hashlib.sha256(machine_info.encode()).hexdigest()
```

---

## 🔄 Auto-Append Workflow

### When Scraping Completes:
1. Job finishes successfully
2. Internal user clicks "Add to Master DB"
3. System reads output CSV
4. For each record:
   - Check if email exists in master DB
   - If exists: Update record with new info
   - If new: Create new record
5. Deduplication ensures email uniqueness
6. Return summary (added, updated, skipped)

### Automatic Trigger (Optional):
Add to `run_job()` in app.py after successful completion:
```python
if user.user_type in ['admin', 'internal']:
    # Auto-append to master database
    append_scraped_results(job_id)
```

---

## 📈 Dashboard Data Source

**Current Implementation:**
```python
@app.route('/dashboard')
def dashboard():
    # Reads from: journal_metrics (in-memory dict)
    # Reads from: job_history (in-memory list)
    total_jobs = sum(m['total_jobs'] for m in journal_metrics.values())
    total_authors = sum(m['total_authors_extracted'] for m in journal_metrics.values())
    # ... etc
```

**With Database (Future):**
```python
@app.route('/dashboard')
@login_required
def dashboard():
    # Read from database tables
    total_jobs = Download.query.count()
    total_records = db.session.query(db.func.sum(Download.total_records)).scalar()
    # ... etc
```

---

## 🎨 Frontend Styling - COMPLETED ✅

### Changes Applied:
- **Navbar**: Black background (#000000)
- **Body**: Off-white background (#fafafa)
- **Buttons**: Purple borders (#805ad5) with hover animations
- **Hover Effects**: Transform + box-shadow on hover
- **Emojis**: Removed from all pages
- **Refresh Button**: Removed from jobs page

### Files Updated:
- `templates/scraper.html` ✅
- `templates/jobs.html` ✅
- `templates/landing.html` - Pending
- `templates/dashboard.html` - Pending

---

## 🚀 Next Steps

### Phase 1: Complete Frontend (1-2 days)
1. Update `landing.html` with new styling
2. Update `dashboard.html` with new styling
3. Create login/register pages
4. Create master database UI
5. Create admin credit management page

### Phase 2: Integrate Credit System (2-3 days)
1. Add authentication to existing routes
2. Replace download endpoint with credit-enabled version
3. Add credit balance display in navbar
4. Add "Buy Credits" functionality
5. Test credit deduction flow

### Phase 3: Master Database Integration (3-4 days)
1. Create upload interface for conference data
2. Add "Append to Master DB" button on completed jobs
3. Implement search interface
4. Add admin download with security
5. Test deduplication logic

### Phase 4: User Management (2-3 days)
1. Create user registration flow
2. Add email verification
3. Implement license validation on login
4. Create admin user management panel
5. Add credit purchase/assignment workflow

### Phase 5: Testing & Deployment (3-4 days)
1. End-to-end testing of all features
2. Security audit
3. Performance testing with large datasets
4. AWS deployment preparation
5. Documentation and training

**Total Estimated Time: 2-3 weeks**

---

## 🔒 Security Considerations

1. **Password Hashing**: Using werkzeug.security
2. **Session Management**: Flask sessions with secret key
3. **SQL Injection**: SQLAlchemy ORM prevents
4. **File Upload**: Validate file types and sizes
5. **Admin Access**: Strict role checking
6. **Machine ID**: Hashed for privacy
7. **Credit Transactions**: Atomic operations with rollback

---

## 📝 Configuration Variables

Add to `app.py` or separate config file:
```python
# Database
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///journal_scraper.db')

# Security
SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret-key')

# Credits
CREDITS_PER_100_RECORDS = 1
XLSX_PREMIUM_MULTIPLIER = 1.2
ADMIN_INITIAL_CREDITS = 999999

# Search History
SEARCH_HISTORY_RETENTION_DAYS = 7

# File Upload
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_UPLOAD_EXTENSIONS = ['csv', 'xlsx']
```

---

## 📞 Support & Maintenance

### Regular Maintenance Tasks:
1. **Daily**: Monitor credit transactions
2. **Weekly**: Cleanup old search history (automated)
3. **Monthly**: Backup master database
4. **Quarterly**: Review user licenses and credits

### Monitoring Queries:
```sql
-- Check total credits in system
SELECT SUM(credits) FROM users;

-- Recent downloads
SELECT * FROM downloads ORDER BY downloaded_at DESC LIMIT 20;

-- Master DB growth
SELECT DATE(created_at), COUNT(*) FROM master_database 
GROUP BY DATE(created_at) ORDER BY DATE(created_at) DESC LIMIT 30;

-- Credit transactions summary
SELECT transaction_type, COUNT(*), SUM(amount) 
FROM credit_transactions 
GROUP BY transaction_type;
```

---

*Last Updated: March 3, 2026 - 10:53 PM IST*
