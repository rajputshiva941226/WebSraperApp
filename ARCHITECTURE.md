# System Architecture - Journal Scraper Web Server

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Web Browser │  │  Mobile App  │  │  API Client  │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                  │                     │
│         └─────────────────┴──────────────────┘                     │
│                           │                                        │
└───────────────────────────┼────────────────────────────────────────┘
                            │
                   HTTP/HTTPS Request
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        WEB SERVER LAYER                             │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │              Nginx (Reverse Proxy)                         │    │
│  │  - SSL/TLS Termination                                     │    │
│  │  - Load Balancing                                          │    │
│  │  - Static File Serving                                     │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
│                             │                                      │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                               │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │         Gunicorn WSGI Server (4 Workers)                   │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
│                             │                                      │
│  ┌──────────────────────────▼─────────────────────────────────┐    │
│  │              Flask Application (web_server.py)             │    │
│  │                                                            │    │
│  │  Routes:                                                   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │ GET  /              → Web Interface                 │   │    │
│  │  │ POST /api/start-scraping → Start Job               │   │    │
│  │  │ GET  /api/job-status/:id → Job Status              │   │    │
│  │  │ GET  /api/jobs      → List All Jobs                │   │    │
│  │  │ GET  /api/download/:id → Download Results          │   │    │
│  │  │ GET  /health        → Health Check                 │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │                                                            │    │
│  │  Components:                                               │    │
│  │  • Request Validation                                      │    │
│  │  • Job Management (active_jobs dict)                       │    │
│  │  • Background Thread Management                            │    │
│  │  • File Serving                                            │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
│                             │                                      │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SCRAPER ADAPTER LAYER                           │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │         scraper_adapter.py (ScraperAdapter)                │    │
│  │                                                            │    │
│  │  Functions:                                                │    │
│  │  • run_bmj_scraper()                                       │    │
│  │  • run_cambridge_scraper()                                 │    │
│  │  • run_europepmc_scraper()                                 │    │
│  │  • _convert_date_format()                                  │    │
│  │  • _find_output_file()                                     │    │
│  └──────────────────────────┬─────────────────────────────────┘    │
│                             │                                      │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│   BMJ Scraper    │ │   Cambridge  │ │   EuropePMC      │
│   (Selenium)     │ │   Scraper    │ │   Scraper (API)  │
├──────────────────┤ ├──────────────┤ ├──────────────────┤
│ • Chrome Driver  │ │ • Chrome     │ │ • HTTP Requests  │
│ • Web Scraping   │ │   Driver     │ │ • JSON Parsing   │
│ • PDF Parsing    │ │ • Web        │ │ • No Browser     │
│ • Email Extract  │ │   Scraping   │ │                  │
└────────┬─────────┘ └──────┬───────┘ └────────┬─────────┘
         │                  │                  │
         └──────────────────┴──────────────────┘
                            │
                            ▼
             ┌──────────────────────────┐
             │  Chrome/ChromeDriver     │
             │  (Selenium WebDriver)    │
             └──────────────────────────┘
                            │
                            ▼
             ┌──────────────────────────┐
             │   Target Journals        │
             │   (Web Pages)            │
             └──────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                │
│                                                                     │
│  ┌────────────────────┐  ┌────────────────────┐                    │
│  │   Results Storage  │  │   Job Metadata     │                    │
│  │   (File System)    │  │   (In-Memory Dict) │                    │
│  ├────────────────────┤  ├────────────────────┤                    │
│  │ • CSV Files        │  │ • Job Status       │                    │
│  │ • Excel Files      │  │ • Timestamps       │                    │
│  │ • /results/        │  │ • Error Messages   │                    │
│  └────────────────────┘  └────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
1. User Submits Job
   │
   ▼
2. Flask Receives Request
   │
   ├─ Validates Input
   ├─ Generates Job ID (UUID)
   ├─ Creates Job Entry in active_jobs{}
   │
   ▼
3. Spawns Background Thread
   │
   ├─ Status: pending → running
   │
   ▼
4. Scraper Adapter
   │
   ├─ Determines Scraper Type
   ├─ Initializes ChromeDriver (if needed)
   ├─ Calls Appropriate Scraper
   │
   ▼
5. Scraper Execution
   │
   ├─ Navigates to Journal Site
   ├─ Searches for Keyword
   ├─ Filters by Date Range
   ├─ Extracts Author Data
   ├─ Collects Emails
   │
   ▼
6. Result Processing
   │
   ├─ Saves to CSV File
   ├─ Moves to /results/ directory
   ├─ Updates Job Status: running → completed
   │
   ▼
7. User Downloads Results
   │
   └─ GET /api/download/:job_id
```

## Component Interaction

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       │ 1. POST /api/start-scraping
       │    { scraper, keyword, dates }
       ▼
┌─────────────┐
│    Flask    │
└──────┬──────┘
       │
       │ 2. Create Job Entry
       │    job_id = UUID()
       │    active_jobs[job_id] = {...}
       ▼
┌──────────────────┐
│ Background Thread│
└──────┬───────────┘
       │
       │ 3. Import Scraper
       │    run_scraper(job_id, ...)
       ▼
┌─────────────────┐
│ Scraper Adapter │
└──────┬──────────┘
       │
       │ 4. Initialize & Run Scraper
       │    scraper.run()
       ▼
┌───────────────┐
│ Actual Scraper│
└──────┬────────┘
       │
       │ 5. Web Scraping
       │    - Open browser
       │    - Navigate & search
       │    - Extract data
       ▼
┌────────────────┐
│  Save Results  │
│  job_id.csv    │
└──────┬─────────┘
       │
       │ 6. Update Job Status
       │    active_jobs[job_id]['status'] = 'completed'
       │    active_jobs[job_id]['output_file'] = path
       ▼
┌─────────────┐
│   Browser   │
│ (Auto Poll) │
└──────┬──────┘
       │
       │ 7. Check Status
       │    GET /api/job-status/:id
       ▼
┌─────────────┐
│    Flask    │
│ Returns Job │
└──────┬──────┘
       │
       │ 8. Download Results
       │    GET /api/download/:id
       ▼
┌─────────────┐
│   Browser   │
│  (CSV File) │
└─────────────┘
```

## Threading Model (Simplified)

```
Main Process
│
├─ Flask Main Thread (handles HTTP requests)
│  │
│  ├─ GET  /              → Render HTML
│  ├─ POST /api/start-scraping → Spawn worker thread
│  ├─ GET  /api/job-status → Return status from active_jobs
│  └─ GET  /api/download  → Send file
│
└─ Background Worker Threads (1 per job)
   │
   ├─ Thread 1: Job abc-123
   │  └─ Running BMJ Scraper
   │
   ├─ Thread 2: Job def-456
   │  └─ Running Cambridge Scraper
   │
   └─ Thread 3: Job ghi-789
      └─ Running EuropePMC Scraper
```

## File Structure

```
journal-scraper-webserver/
│
├── web_server.py           # Main Flask application
├── scraper_adapter.py      # Scraper standardization layer
├── config.py               # Configuration file
│
├── bmjjournal_selenium.py  # Individual scrapers
├── cambridge_scraper.py    # (your existing scrapers)
├── europepmc_scraper.py
│
├── templates/
│   └── index.html          # Web UI
│
├── results/                # Output directory
│   ├── job-1_bmj.csv
│   ├── job-2_cambridge.csv
│   └── ...
│
├── logs/                   # Application logs
│   └── scraper_server.log
│
├── requirements.txt        # Python dependencies
├── README.md              # Main documentation
├── DEPLOYMENT.md          # Deployment guide
└── ARCHITECTURE.md        # This file
```

## Technology Stack

```
┌─────────────────────────────────────┐
│          Frontend                   │
├─────────────────────────────────────┤
│ • HTML5                             │
│ • CSS3 (Vanilla)                    │
│ • JavaScript (Vanilla)              │
│ • Fetch API                         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│          Backend                    │
├─────────────────────────────────────┤
│ • Python 3.8+                       │
│ • Flask 3.0                         │
│ • Threading (stdlib)                │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│       Web Scraping                  │
├─────────────────────────────────────┤
│ • Selenium 4.16                     │
│ • ChromeDriver (webdriver-manager)  │
│ • undetected-chromedriver           │
│ • lxml                              │
│ • BeautifulSoup4                    │
│ • requests                          │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│       Production (Optional)         │
├─────────────────────────────────────┤
│ • Gunicorn (WSGI Server)            │
│ • Nginx (Reverse Proxy)             │
│ • Docker (Containerization)         │
│ • Let's Encrypt (SSL)               │
└─────────────────────────────────────┘
```

## Security Architecture

```
Internet
   │
   ▼
┌────────────┐
│  Firewall  │  ← Ports: 80, 443
└─────┬──────┘
      │
      ▼
┌────────────┐
│   Nginx    │  ← SSL/TLS, Rate Limiting
└─────┬──────┘
      │
      ▼
┌────────────┐
│ Gunicorn   │  ← WSGI, Process Isolation
└─────┬──────┘
      │
      ▼
┌────────────┐
│   Flask    │  ← Input Validation, CSRF Protection
└─────┬──────┘
      │
      ▼
┌────────────┐
│ File System│  ← Restricted Permissions
└────────────┘
```

## Scalability Considerations

### Current (Simple) Architecture:
- Single server
- In-memory job storage
- File-based results
- Threading for concurrency

### Future Enhancements (Production Scale):

```
┌─────────────┐     ┌─────────────┐
│ Load        │────→│   Server 1  │
│ Balancer    │     └─────────────┘
└─────┬───────┘     ┌─────────────┐
      │        ────→│   Server 2  │
      │             └─────────────┘
      │             ┌─────────────┐
      └────────────→│   Server 3  │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Redis    │  ← Job Queue
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  PostgreSQL │  ← Job Metadata
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │     S3      │  ← Results Storage
                    └─────────────┘
```

## Monitoring Architecture

```
Application
   │
   ├─→ Application Logs → log files → Log Aggregator (ELK/Splunk)
   │
   ├─→ Metrics → Prometheus → Grafana Dashboard
   │
   └─→ Health Checks → Uptime Monitor → Alerts
```

---

This architecture is designed to be:
- **Simple**: Easy to understand and deploy
- **Modular**: Easy to add new scrapers
- **Scalable**: Can be enhanced for production
- **Maintainable**: Clear separation of concerns
