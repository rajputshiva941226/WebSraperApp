# Journal Scraper Web Server

A simple Flask-based web application for scraping author emails and names from academic journals.

## Features

- 🌐 Clean web interface for submitting scraping jobs
- 📊 Real-time job status tracking
- 📥 Download results as CSV files
- 🔄 Auto-refresh job status every 5 seconds
- 🎯 Support for multiple journal scrapers:
  - BMJ Journals
  - Cambridge University Press
  - Europe PMC
  - (Easy to add more)

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────────┐
│  Flask Server   │
│  (Port 5000)    │
└──────┬──────────┘
       │
       ├──── Background Thread ──┐
       │                         │
       ▼                         ▼
┌─────────────┐         ┌──────────────┐
│  Job Queue  │         │   Scrapers   │
│  (In-Memory)│         │  - BMJ       │
└─────────────┘         │  - Cambridge │
                        │  - EuropePMC │
                        └──────┬───────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ CSV Results  │
                        │   (Disk)     │
                        └──────────────┘
```

## Setup Instructions

### 1. Prerequisites

- Python 3.8 or higher
- Chrome browser (for Selenium-based scrapers)
- Internet connection

### 2. Installation

```bash
# Clone or download the project
cd journal-scraper-webserver

# Install dependencies
pip install -r requirements.txt
```

### 3. Project Structure

```
journal-scraper-webserver/
├── web_server.py              # Main Flask application
├── templates/
│   └── index.html             # Web interface
├── requirements.txt           # Python dependencies
├── results/                   # Output directory (auto-created)
├── bmjjournal_selenium.py     # BMJ scraper
├── cambridge_scraper.py       # Cambridge scraper
├── europepmc_scraper.py       # EuropePMC scraper
└── README.md                  # This file
```

### 4. Running the Server

```bash
python web_server.py
```

The server will start on `http://localhost:5000`

## Usage

### Web Interface

1. Open `http://localhost:5000` in your browser
2. Fill in the form:
   - **Select Journal**: Choose from available scrapers
   - **Search Keyword**: Enter your search term (e.g., "cancer research")
   - **Date Range**: Select start and end dates
3. Click "Start Scraping"
4. Monitor job progress in the "Scraping Jobs" section
5. Download results when the job completes

### API Endpoints

#### Start a Scraping Job

```bash
POST /api/start-scraping
Content-Type: application/json

{
  "scraper": "bmj",
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

#### Check Job Status

```bash
GET /api/job-status/{job_id}
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "scraper": "bmj",
  "scraper_name": "BMJ Journals",
  "keyword": "cancer research",
  "start_date": "01/01/2023",
  "end_date": "12/31/2023",
  "status": "completed",
  "created_at": "2024-02-13T10:30:00",
  "end_time": "2024-02-13T10:45:00",
  "output_file": "results/550e8400-e29b-41d4-a716-446655440000_bmj_results.csv"
}
```

#### List All Jobs

```bash
GET /api/jobs
```

#### Download Results

```bash
GET /api/download/{job_id}
```

## Adding New Scrapers

To add a new scraper, edit `web_server.py`:

```python
SCRAPERS = {
    'your_scraper': {
        'name': 'Your Journal Name',
        'module': 'your_scraper_module',
        'class': 'YourScraperClass'
    },
    # ... existing scrapers
}
```

Then add the import and initialization logic in the `run_scraper_task()` function.

## Configuration

### Memory Usage

By default, the server uses in-memory storage for job tracking. For production:

- Consider using Redis for job queue
- Implement persistent storage (PostgreSQL/MongoDB)
- Add Celery for better background task management

### Performance

- Each scraper runs in a separate thread
- For multiple concurrent users, consider using Celery workers
- Results are stored in the `results/` directory

## Troubleshooting

### ChromeDriver Issues

If you get ChromeDriver errors:

```bash
# The webdriver-manager will auto-download the correct version
# But you can manually specify:
pip install webdriver-manager --upgrade
```

### Port Already in Use

Change the port in `web_server.py`:

```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Change 5000 to 5001
```

### Scrapers Not Working

Make sure your scraper files are in the same directory as `web_server.py` and have the correct class names.

## Deployment

### Production Deployment

For production, use a proper WSGI server:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 web_server:app
```

### Docker Deployment (Optional)

Create a `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install Chrome for Selenium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "web_server.py"]
```

## Security Considerations

🔒 **Important for Production:**

1. Change the `SECRET_KEY` in `web_server.py`
2. Add authentication/authorization
3. Implement rate limiting
4. Use HTTPS (SSL/TLS)
5. Validate and sanitize all user inputs
6. Set proper CORS policies

## License

This project is for academic/research purposes.

## Support

For issues or questions, please check:
- Server logs in the terminal
- Browser console (F12) for frontend errors
- Job status in the web interface
