#!/usr/bin/env python3
"""
Quick deployment script to fix celery_worker.py on the server.
Run this on the EC2 server to apply the ChromeDriver conditional fix.
"""

import os
import sys

# Path to celery_worker.py
celery_worker_path = '/var/www/journal-scraper/celery_worker.py'

# Read the current file
with open(celery_worker_path, 'r') as f:
    content = f.read()

# Check if fix is already applied
if 'api_scrapers = {' in content:
    print("✓ Fix already applied!")
    sys.exit(0)

# Find and replace the old code
old_code = """        from scraper_adapter import ScraperAdapter
        from webdriver_manager.chrome import ChromeDriverManager

        driver_path = ChromeDriverManager().install()

        with flask_app.app_context():"""

new_code = """        from scraper_adapter import ScraperAdapter
        
        # Only install ChromeDriver for Selenium-based scrapers
        # API scrapers (europepmc, pubmed) don't need Chrome
        api_scrapers = {'europepmc', 'pubmed'}
        driver_path = None
        
        if journal not in api_scrapers:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()

        with flask_app.app_context():"""

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(celery_worker_path, 'w') as f:
        f.write(content)
    print("✓ Fix applied successfully!")
    print("\nNow restart Celery:")
    print("  sudo systemctl restart journal-scraper-celery")
else:
    print("✗ Could not find the code to replace. File may have been modified.")
    sys.exit(1)
