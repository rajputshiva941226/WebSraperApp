# Journal Scraper Web Server - Complete Guide

## 📋 Overview

A **production-aligned** web scraping system for extracting author contact information from academic journals. This implementation follows the requirements document but uses a **simplified architecture** (file-based storage instead of database) for easy deployment and future database migration.

## 🎯 Key Features (Aligned with Requirements)

### ✅ Implemented Features

- **Multi-Journal Support**: Currently supports BMJ, Cambridge, EuropePMC (8 more journals can be added)
- **Real-Time Dashboard**: Live metrics, success rates, per-journal analytics
- **Job Queue Management**: Background processing with threading
- **Advanced Email Extraction**: Author names, emails, affiliations
- **Metrics Tracking**: Per-journal statistics, success rates, processing times
- **File-Based Storage**: JSON for metrics (easy to migrate to PostgreSQL later)
- **RESTful API**: Complete API for programmatic access
- **Modern UI**: Responsive web interface with real-time updates

### 🔄 Future Enhancements (From Requirements Document)

These can be added when needed:
- PDF Processing with GROBID
- Co-author data separation
- Multi-tab scraping with segregated exports
- Multi-affiliation handling
- WebSocket for real-time updates
- Celery + Redis for job queue
- PostgreSQL for persistent storage
- User authentication (JWT)
- Email notifications

## 🏗️ Architecture

### Current (Simplified)

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Flask App  │ ← Web UI + API
│  (app.py)   │
└──────┬──────┘
       │
       ├─→ Scraper Adapter ─→ Your Scrapers
       ├─→ Job Management (In-Memory + JSON)
       └─→ Metrics Tracking (JSON Files)
```

### Future (Production Scale)

```
Load Balancer → Nginx → Gunicorn → Flask App
                                      ├─→ Celery Workers
                                      ├─→ PostgreSQL
                                      ├─→ Redis
                                      └─→ Selenium Grid
```

## 📊 Dashboard Features

### Overall Statistics
- Total jobs run
- Success rate percentage
- Total authors extracted
- Total emails collected
- Active jobs count
- Failed jobs count

### Per-Journal Metrics
- Total jobs per journal
- Success rate (with visual progress bar)
- Authors extracted
- Emails collected
- Average processing time
- Last run timestamp

### Recent Jobs View
- Last 10 jobs with status
- Quick access from dashboard

## 🚀 Getting Started

### Installation

```bash
# Clone the repository
cd journal-scraper-webserver

# Install dependencies
pip install -r requirements.txt

# Copy your scraper files
cp /path/to/bmjjournal_selenium.py .
cp /path/to/cambridge_scraper.py .
cp /path/to/europepmc_scraper.py .
```

### Running the Server

```bash
python app.py
```

Access the application:
- **Main Interface**: http://localhost:5000
- **Dashboard**: http://localhost:5000/dashboard
- **Jobs Manager**: http://localhost:5000/jobs

## 📁 Directory Structure

```
journal-scraper-webserver/
├── app.py                      # Main Flask application
├── scraper_adapter.py          # Scraper interface
├── config.py                   # Configuration (optional)
│
├── templates/                  # HTML templates
│   ├── landing.html           # Home page
│   ├── dashboard.html         # Metrics dashboard
│   ├── scraper.html           # Scraping form
│   └── jobs.html              # Jobs manager
│
├── data/                       # Persisted data (auto-created)
│   └── metrics.json           # Journal metrics
│
├── results/                    # Scraping results (auto-created)
│   ├── job-1_bmj.csv
│   └── job-2_cambridge.csv
│
├── logs/                       # Application logs (auto-created)
│
├── requirements.txt            # Python dependencies
├── README.md                   # This file
└── DEPLOYMENT.md               # Production deployment guide
```

## 🔧 Configuration

The system is configured in `app.py`. Key settings:

```python
# Storage
app.config['UPLOAD_FOLDER'] = 'results'
app.config['DATA_FOLDER'] = 'data'

# Journals Configuration
JOURNALS = {
    'bmj': {
        'name': 'BMJ Journals',
        'enabled': True,
        # ... more settings
    }
}
```

## 📡 API Endpoints

### Start Scraping Job

```bash
POST /api/start-scraping
Content-Type: application/json

{
  "journal": "bmj",
  "keyword": "cancer research",
  "start_date": "01/01/2023",
  "end_date": "12/31/2023"
}
```

Response:
```json
{
  "success": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Scraping job started successfully"
}
```

### Get Job Status

```bash
GET /api/job-status/{job_id}
```

### List All Jobs

```bash
GET /api/jobs
```

### Download Results

```bash
GET /api/download/{job_id}
```

### Get Metrics

```bash
GET /api/metrics              # All metrics
GET /api/metrics/{journal}    # Specific journal
```

### Health Check

```bash
GET /health
```

## 📊 Data Persistence

Currently uses JSON files (simple, no database needed):

```
data/
└── metrics.json              # Contains:
    ├── journal_metrics       # Per-journal stats
    └── job_history          # Last 1000 jobs
```

### Migrating to Database (Future)

The data structure is designed for easy PostgreSQL migration:

```python
# Current (JSON)
journal_metrics = {
    'bmj': {
        'total_jobs': 10,
        'successful_jobs': 8,
        ...
    }
}

# Future (PostgreSQL)
CREATE TABLE journal_metrics (
    journal VARCHAR(50) PRIMARY KEY,
    total_jobs INT,
    successful_jobs INT,
    ...
);
```

## 🎨 Adding New Journals

### Step 1: Add Journal Configuration

Edit `app.py`:

```python
JOURNALS = {
    'your_journal': {
        'name': 'Your Journal Name',
        'full_name': 'Full Official Name',
        'type': 'selenium',  # or 'api'
        'enabled': True,
        'icon': '📖',
        'description': 'Brief description'
    },
    # ... existing journals
}
```

### Step 2: Add Scraper Function

Edit `scraper_adapter.py`:

```python
def run_your_journal_scraper(self, keyword, start_date, end_date, driver_path):
    from your_journal_scraper import YourScraperClass
    scraper = YourScraperClass(keyword, start_date, end_date, driver_path)
    # ... handle output
    return output_file
```

### Step 3: Update Main Adapter

```python
# In scraper_adapter.py run_scraper() function
elif scraper_type == 'your_journal':
    return adapter.run_your_journal_scraper(keyword, start_date, end_date, driver_path)
```

That's it! The journal will now appear in the UI and be fully functional.

## 📈 Monitoring & Analytics

### Dashboard Metrics

The dashboard automatically tracks:
- **Success Rate**: Percentage of successful jobs
- **Processing Time**: Average time per journal
- **Volume**: Authors and emails extracted
- **Status**: Real-time job status

### Viewing Job History

```bash
# Jobs are persisted in data/metrics.json
# Last 1000 jobs are kept automatically
```

### Manual Metrics Access

```python
# Load metrics programmatically
import json
with open('data/metrics.json', 'r') as f:
    data = json.load(f)
    print(data['journal_metrics'])
```

## 🚀 Production Deployment

### Simple Production (Single Server)

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 app:app
```

### With Nginx (Recommended)

See `DEPLOYMENT.md` for complete Nginx setup

### Docker Deployment

```bash
# Build
docker build -t journal-scraper .

# Run
docker run -d -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/results:/app/results \
  journal-scraper
```

## 🔐 Security

### Current Implementation
- Basic security (suitable for internal use)
- No authentication required
- No rate limiting

### Production Recommendations
1. Add authentication (JWT or session-based)
2. Implement rate limiting
3. Use HTTPS (SSL/TLS)
4. Add input validation
5. Implement CORS policies
6. Use environment variables for secrets

## 🧪 Testing

### Manual Testing

1. Start the server: `python app.py`
2. Open http://localhost:5000
3. Submit a test job with a small date range
4. Monitor progress on Jobs page
5. Check Dashboard for updated metrics

### API Testing

```bash
# Start a job
curl -X POST http://localhost:5000/api/start-scraping \
  -H "Content-Type: application/json" \
  -d '{"journal":"europepmc","keyword":"test","start_date":"01/01/2024","end_date":"01/31/2024"}'

# Check status
curl http://localhost:5000/api/job-status/{job_id}

# Get metrics
curl http://localhost:5000/api/metrics
```

## 🐛 Troubleshooting

### Jobs Not Starting

Check:
1. Scraper files are in the correct directory
2. ChromeDriver is installed: `pip install webdriver-manager`
3. Check logs for errors

### Dashboard Shows Zero Metrics

Metrics are saved after job completion. Run a job first.

### Results Not Downloading

1. Check `results/` directory exists
2. Verify job status is "completed"
3. Check job output_file path in metrics.json

## 📦 Data Structure

### Job Object

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "journal": "bmj",
  "journal_name": "BMJ Journals",
  "keyword": "cancer research",
  "start_date": "01/01/2023",
  "end_date": "12/31/2023",
  "status": "completed",
  "created_at": "2024-02-13T10:00:00",
  "end_time": "2024-02-13T10:15:00",
  "duration": 900.5,
  "authors_count": 150,
  "emails_count": 120,
  "output_file": "results/550e8400_bmj_results.csv",
  "message": "✅ Completed! Found 150 authors, 120 emails"
}
```

### Metrics Object

```json
{
  "journal_metrics": {
    "bmj": {
      "total_jobs": 10,
      "successful_jobs": 8,
      "failed_jobs": 2,
      "total_authors_extracted": 1500,
      "total_emails_extracted": 1200,
      "avg_processing_time": 850.5,
      "last_run": "2024-02-13T10:15:00"
    }
  },
  "job_history": [ /* last 1000 jobs */ ]
}
```

## 🔄 Migration Path to Full System

When ready for the full production system from the requirements document:

### Phase 1: Add Database (Week 1)
```python
# Replace JSON with PostgreSQL
# Keep API endpoints the same
pip install psycopg2-binary sqlalchemy
```

### Phase 2: Add Celery (Week 2)
```python
# Replace threading with Celery
pip install celery redis
```

### Phase 3: Add Advanced Features (Weeks 3-4)
- PDF processing with GROBID
- Multi-tab scraping
- Co-author separation
- WebSocket updates

### Phase 4: Scale Infrastructure (Week 5)
- Selenium Grid
- Multiple workers
- Load balancing

## 💡 Best Practices

### 1. Regular Backups

```bash
# Backup metrics
cp data/metrics.json data/metrics_backup_$(date +%Y%m%d).json

# Backup results
tar -czf results_backup_$(date +%Y%m%d).tar.gz results/
```

### 2. Monitoring Disk Space

```bash
# Check results directory size
du -sh results/

# Clean old results (older than 30 days)
find results/ -name "*.csv" -mtime +30 -delete
```

### 3. Log Rotation

Logs are printed to console. For production:

```bash
# Run with logging
python app.py 2>&1 | tee logs/app.log
```

## 📞 Support

### Common Issues

1. **Port 5000 in use**: Change port in `app.py`
2. **Chrome not found**: Install Chrome browser
3. **Metrics not persisting**: Check `data/` directory permissions

### Getting Help

1. Check this README
2. Review `DEPLOYMENT.md` for production setup
3. Check application logs
4. Verify API responses with curl

## 📝 License

This project is for academic/research purposes.

---

**Version**: 2.0 (Enhanced with Dashboard)  
**Last Updated**: February 2024  
**Aligned with**: Requirements Document (Simplified Implementation)
