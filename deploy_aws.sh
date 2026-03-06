#!/bin/bash

################################################################################
# AWS EC2 Deployment Script for Journal Scraper Web Application
# This script automates the deployment process to AWS EC2
################################################################################

set -e  # Exit on error

echo "=========================================="
echo "AWS EC2 Deployment Script"
echo "=========================================="
echo ""

# Configuration
APP_NAME="journal-scraper"
APP_DIR="/var/www/journal-scraper"
PYTHON_VERSION="python3"
SERVICE_NAME="journal-scraper"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root or with sudo"
    exit 1
fi

print_status "Starting deployment process..."

# Update system packages
print_status "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install required system packages
print_status "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    supervisor \
    git \
    curl \
    wget \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev

# Install Chrome and ChromeDriver for Selenium
print_status "Installing Google Chrome..."
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt-get install -y ./google-chrome-stable_current_amd64.deb || true
rm google-chrome-stable_current_amd64.deb

print_status "Installing ChromeDriver..."
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION%%.*}")
wget -q "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip -o chromedriver_linux64.zip
mv chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver
rm chromedriver_linux64.zip

# Create application directory
print_status "Setting up application directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# Create app user if doesn't exist
if ! id "appuser" &>/dev/null; then
    print_status "Creating application user..."
    useradd -r -s /bin/bash -d $APP_DIR appuser
fi

# Clone or pull latest code
if [ -d ".git" ]; then
    print_status "Pulling latest changes from repository..."
    git pull origin main || git pull origin master
else
    print_status "Repository not found. Please clone manually first."
    print_warning "Run: git clone <your-repo-url> $APP_DIR"
    exit 1
fi

# Create virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON_VERSION -m venv venv
fi

# Activate virtual environment and install dependencies
print_status "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn  # Production WSGI server

# Create necessary directories
print_status "Creating application directories..."
mkdir -p instance
mkdir -p logs
mkdir -p results
mkdir -p data

# Create production configuration file
print_status "Creating production configuration..."
cat > instance/config.py << 'EOF'
import os

# Production Configuration
SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-to-random-secret-key-in-production'
SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/journal_scraper.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False
DEBUG = False
TESTING = False

# Security settings
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# File upload settings
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
UPLOAD_FOLDER = 'results'
DATA_FOLDER = 'data'
EOF

# Initialize database if doesn't exist
if [ ! -f "instance/journal_scraper.db" ]; then
    print_status "Initializing database..."
    python init_database.py
fi

# Run database migrations
if [ -f "migrate_database_simple.py" ]; then
    print_status "Running database migrations..."
    echo "y" | python migrate_database_simple.py || print_warning "Migration may have already run"
fi

# Set proper permissions
print_status "Setting file permissions..."
chown -R appuser:appuser $APP_DIR
chmod -R 755 $APP_DIR
chmod 600 instance/journal_scraper.db 2>/dev/null || true

# Create Gunicorn systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Journal Scraper Web Application
After=network.target

[Service]
Type=notify
User=appuser
Group=appuser
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 127.0.0.1:5000 --timeout 300 --access-logfile $APP_DIR/logs/access.log --error-logfile $APP_DIR/logs/error.log app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx as reverse proxy
print_status "Configuring Nginx..."
cat > /etc/nginx/sites-available/$APP_NAME << 'EOF'
server {
    listen 80;
    server_name _;  # Replace with your domain

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /static {
        alias /var/www/journal-scraper/static;
        expires 30d;
    }

    location /results {
        alias /var/www/journal-scraper/results;
        internal;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
print_status "Testing Nginx configuration..."
nginx -t

# Reload systemd and start services
print_status "Starting services..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME
systemctl restart nginx

# Configure firewall if UFW is available
if command -v ufw &> /dev/null; then
    print_status "Configuring firewall..."
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
fi

# Check service status
print_status "Checking service status..."
sleep 3
systemctl status $SERVICE_NAME --no-pager || print_warning "Service may be starting..."

echo ""
echo "=========================================="
print_status "Deployment completed successfully!"
echo "=========================================="
echo ""
echo "Service Status:"
systemctl is-active $SERVICE_NAME && echo "✓ Application: Running" || echo "✗ Application: Stopped"
systemctl is-active nginx && echo "✓ Nginx: Running" || echo "✗ Nginx: Stopped"
echo ""
echo "Useful Commands:"
echo "  View logs:        journalctl -u $SERVICE_NAME -f"
echo "  Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  Check status:     sudo systemctl status $SERVICE_NAME"
echo "  Nginx logs:       tail -f /var/log/nginx/error.log"
echo ""
echo "Access your application at: http://$(curl -s ifconfig.me)"
echo "=========================================="
