"""
Configuration file for Journal Scraper Web Server
Modify these settings as needed
"""

# Server Configuration
SERVER_CONFIG = {
    'host': '0.0.0.0',  # Listen on all network interfaces
    'port': 5000,        # Server port
    'debug': True,       # Debug mode (set to False in production)
}

# Security
SECRET_KEY = 'change-this-to-a-random-secret-key-in-production'

# File Storage
UPLOAD_FOLDER = 'results'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size

# Scraper Settings
SCRAPER_SETTINGS = {
    'timeout': 300,  # Maximum time (seconds) for a scraper to run
    'retry_attempts': 3,  # Number of retry attempts on failure
    'delay_between_retries': 5,  # Delay in seconds between retries
}

# Job Management
JOB_SETTINGS = {
    'max_concurrent_jobs': 5,  # Maximum number of concurrent scraping jobs
    'job_history_limit': 100,  # Maximum number of jobs to keep in memory
    'auto_cleanup_completed': False,  # Automatically remove completed jobs from memory
    'cleanup_age_hours': 24,  # Remove jobs older than X hours
}

# Logging
LOGGING_CONFIG = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'scraper_server.log',  # Log file name (None to disable file logging)
}

# Chrome/Selenium Settings
CHROME_OPTIONS = [
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    # Uncomment the next line to run Chrome in headless mode
    # '--headless',
]

# Available Scrapers
# Add or remove scrapers here
SCRAPERS = {
    'bmj': {
        'name': 'BMJ Journals',
        'module': 'bmjjournal_selenium',
        'class': 'BMJJournalScraper',
        'type': 'selenium',
        'enabled': True,
    },
    'cambridge': {
        'name': 'Cambridge University Press',
        'module': 'cambridge_scraper',
        'class': 'CambridgeScraper',
        'type': 'selenium',
        'enabled': True,
    },
    'europepmc': {
        'name': 'Europe PMC',
        'module': 'europepmc_scraper',
        'class': 'EuropePMCScraper',
        'type': 'api',
        'enabled': True,
    },
    # Add more scrapers here following the same pattern
    # 'oxford': {
    #     'name': 'Oxford Academic',
    #     'module': 'oxford_scraper',
    #     'class': 'OxfordScraper',
    #     'type': 'selenium',
    #     'enabled': True,
    # },
}

# API Rate Limiting (Future enhancement)
RATE_LIMIT_CONFIG = {
    'enabled': False,
    'requests_per_minute': 10,
    'requests_per_hour': 100,
}

# Email Notifications (Future enhancement)
EMAIL_CONFIG = {
    'enabled': False,
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'your-email@gmail.com',
    'sender_password': 'your-app-password',
    'notify_on_completion': True,
    'notify_on_failure': True,
}
