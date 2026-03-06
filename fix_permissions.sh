#!/bin/bash
# Fix directory permissions for ubuntu user to run Celery worker

echo "Fixing directory permissions..."

# Fix results directory
sudo chown -R ubuntu:ubuntu /var/www/journal-scraper/results
sudo chmod -R 755 /var/www/journal-scraper/results

# Fix data directory
sudo chown -R ubuntu:ubuntu /var/www/journal-scraper/data
sudo chmod -R 755 /var/www/journal-scraper/data

# Fix logs directory
sudo mkdir -p /var/log/journal-scraper
sudo chown -R ubuntu:ubuntu /var/log/journal-scraper
sudo chmod -R 755 /var/log/journal-scraper

# Fix database file if using SQLite
if [ -f /var/www/journal-scraper/journal_scraper.db ]; then
    sudo chown ubuntu:ubuntu /var/www/journal-scraper/journal_scraper.db
    sudo chmod 644 /var/www/journal-scraper/journal_scraper.db
fi

echo "✓ Directory permissions fixed"
echo ""
echo "Now restart Celery:"
echo "  sudo systemctl restart journal-scraper-celery"
