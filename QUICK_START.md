# Journal Scraper Web Server - Quick Start Guide

## 🎯 What You've Got

A **simple, production-ready web application** that wraps your existing journal scrapers with a clean web interface.

### Key Features:
✅ **Web Interface** - Beautiful, responsive UI for submitting scraping jobs  
✅ **Real-time Status** - Live updates on job progress  
✅ **Auto-download** - Download results as CSV when complete  
✅ **Multi-scraper Support** - BMJ, Cambridge, EuropePMC (easily add more)  
✅ **Simple Architecture** - No complex dependencies, easy to deploy  
✅ **Production Ready** - Includes deployment guides for cloud hosting  

---

## 📦 What's Included

```
Your Complete Package:
│
├── 🌐 Core Application
│   ├── web_server.py          # Flask web server
│   ├── scraper_adapter.py     # Scraper standardization
│   ├── config.py              # Configuration
│   └── templates/index.html   # Web UI
│
├── 🚀 Quick Start Scripts
│   ├── start.sh               # Linux/Mac startup
│   ├── start.bat              # Windows startup
│   └── requirements.txt       # Dependencies
│
├── 📚 Documentation
│   ├── README.md              # Main guide
│   ├── ARCHITECTURE.md        # System design
│   ├── DEPLOYMENT.md          # Production deployment
│   └── QUICK_START.md         # This file
│
└── 🔧 Configuration
    ├── config.py              # Settings
    └── .gitignore             # Git exclusions
```

---

## 🚀 Get Started in 3 Steps

### Step 1: Setup

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```bash
start.bat
```

**Manual Setup:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Add Your Scrapers

Copy your scraper files to the project directory:
```
journal-scraper-webserver/
├── web_server.py
├── bmjjournal_selenium.py      ← Your scrapers
├── cambridge_scraper.py         ← go here
├── europepmc_scraper.py         ←
└── ...
```

### Step 3: Run

```bash
python web_server.py
```

Open your browser to: **http://localhost:5000**

---

## 🎨 How It Works

### 1. User Submits a Job

```
┌─────────────────────────┐
│   Web Browser           │
│                         │
│  [Select Journal    ▼]  │
│  [Keyword: cancer   ]   │
│  [Start: 01/01/2023 ]   │
│  [End:   12/31/2023 ]   │
│                         │
│    [🚀 Start Scraping]  │
└─────────────────────────┘
```

### 2. Server Processes in Background

```
Flask Server
  └─> Creates Job (UUID)
      └─> Spawns Background Thread
          └─> Runs Your Scraper
              └─> Saves Results to CSV
```

### 3. User Downloads Results

```
┌─────────────────────────┐
│   Scraping Jobs         │
│                         │
│  ✅ BMJ Journals        │
│     Status: Completed   │
│     [📥 Download]       │
└─────────────────────────┘
```

---

## 🎯 Simple Architecture

```
Browser → Flask → Adapter → Your Scraper → CSV File
   ↓                                          ↓
  UI                                      Download
```

**That's it!** No complex databases, no message queues, no microservices.  
Just a simple, effective web server that does what you need.

---

## 📝 Using the API

### Start a Job
```bash
curl -X POST http://localhost:5000/api/start-scraping \
  -H "Content-Type: application/json" \
  -d '{
    "scraper": "bmj",
    "keyword": "cancer research",
    "start_date": "01/01/2023",
    "end_date": "12/31/2023"
  }'
```

### Check Status
```bash
curl http://localhost:5000/api/job-status/JOB_ID
```

### Download Results
```bash
curl http://localhost:5000/api/download/JOB_ID -o results.csv
```

---

## 🔧 Adding a New Scraper

**1. Add to config.py:**
```python
SCRAPERS = {
    'your_scraper': {
        'name': 'Your Journal Name',
        'module': 'your_scraper_file',
        'class': 'YourScraperClass',
        'type': 'selenium',  # or 'api'
        'enabled': True,
    },
    # ... existing scrapers
}
```

**2. Add to scraper_adapter.py:**
```python
def run_your_scraper(self, keyword, start_date, end_date, driver_path):
    from your_scraper_file import YourScraperClass
    scraper = YourScraperClass(keyword, start_date, end_date, driver_path)
    # ... handle output
    return output_file
```

**That's all!** Your new scraper is now available in the web interface.

---

## 🌐 Deploying to Production

### Quick Production Setup

**1. Use Gunicorn:**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 web_server:app
```

**2. Add Nginx (optional):**
- See `DEPLOYMENT.md` for Nginx configuration
- Adds SSL/HTTPS support
- Better performance

**3. Deploy to Cloud:**
Choose your platform:
- **AWS EC2** - See `DEPLOYMENT.md` → AWS Section
- **DigitalOcean** - See `DEPLOYMENT.md` → DigitalOcean Section
- **Google Cloud** - See `DEPLOYMENT.md` → GCP Section

### Docker Deployment (Simple)

```bash
# Build
docker build -t journal-scraper .

# Run
docker run -d -p 5000:5000 journal-scraper
```

---

## 🛠 Configuration

Edit `config.py` to customize:

```python
# Change port
SERVER_CONFIG = {
    'port': 8080,  # Default is 5000
}

# Add Chrome options
CHROME_OPTIONS = [
    '--headless',  # Run Chrome in background
    '--no-sandbox',
]

# Adjust timeouts
SCRAPER_SETTINGS = {
    'timeout': 600,  # 10 minutes
}
```

---

## 🔍 Monitoring

### Check Server Health
```bash
curl http://localhost:5000/health
```

### View Active Jobs
```bash
curl http://localhost:5000/api/jobs
```

### Check Logs
```bash
tail -f scraper_server.log
```

---

## 🐛 Troubleshooting

### Chrome/Selenium Issues
```bash
# Reinstall webdriver-manager
pip install --upgrade webdriver-manager
```

### Port Already in Use
```python
# Change port in config.py
SERVER_CONFIG = {'port': 5001}
```

### Scraper Not Found
- Ensure scraper files are in the same directory
- Check module names match in `config.py`
- Verify imports work: `python -c "import bmjjournal_selenium"`

---

## 📚 Next Steps

1. ✅ **Test Locally** - Run the server and test with sample data
2. ✅ **Add Your Scrapers** - Copy your existing scrapers
3. ✅ **Customize** - Edit `config.py` to suit your needs
4. 📖 **Read ARCHITECTURE.md** - Understand how it works
5. 🚀 **Deploy** - Follow `DEPLOYMENT.md` for production

---

## 💡 Pro Tips

### Tip 1: Multiple Scrapers at Once
Submit multiple jobs - they run in parallel!

### Tip 2: Date Range Strategy
For large date ranges, the system automatically processes monthly chunks (from your existing `main_app.py` logic).

### Tip 3: Results Management
Results are stored in `results/` directory. Set up automated cleanup:
```bash
# Delete results older than 7 days
find results/ -name "*.csv" -mtime +7 -delete
```

### Tip 4: Run in Background
```bash
# Linux/Mac
nohup python web_server.py > server.log 2>&1 &

# Or use screen
screen -S scraper
python web_server.py
# Press Ctrl+A, then D to detach
```

---

## 🎓 Architecture Summary

**Simple, Not Simplistic**

This system uses a straightforward architecture that's:
- ✅ **Easy to understand** - No complex abstractions
- ✅ **Easy to deploy** - No external dependencies required
- ✅ **Easy to extend** - Add scrapers in minutes
- ✅ **Production capable** - Can handle real workloads

**What it does well:**
- Web interface for non-technical users
- Background processing without blocking
- File-based results (simple and reliable)
- Real-time status updates

**What it doesn't do (yet):**
- Distributed processing (single server only)
- Persistent job storage (jobs lost on restart)
- User authentication (open access)
- Advanced queuing (Celery/Redis)

*These can be added later if needed - see the requirements document for that architecture.*

---

## 🆘 Getting Help

1. Check the logs: `scraper_server.log`
2. Review `README.md` for detailed docs
3. See `ARCHITECTURE.md` for system design
4. Read `DEPLOYMENT.md` for production setup

---

## ✨ Summary

You now have a **simple, working web server** that:
- Takes input from users via a web form
- Runs your existing scrapers in the background
- Returns results as downloadable CSV files
- Can be deployed to production with minimal effort

**Start it up and give it a try!** 🚀

```bash
python web_server.py
```

Then open: **http://localhost:5000**

---

*Made with simplicity in mind. Keep it simple, keep it working.* 👍
