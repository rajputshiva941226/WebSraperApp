#!/bin/bash

################################################################################
# Deployment Script for Already Cloned Repository
# Use this when repository is already cloned to /var/www/journal-scraper
################################################################################

set -e

APP_DIR="/var/www/journal-scraper"
SERVICE_NAME="journal-scraper"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

echo "=========================================="
echo "Journal Scraper Deployment"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root: sudo ./deploy_existing.sh"
    exit 1
fi

# Verify we're in the right directory
if [ ! -f "$APP_DIR/app.py" ]; then
    print_error "app.py not found in $APP_DIR"
    print_error "Please ensure code is cloned to $APP_DIR"
    exit 1
fi

cd $APP_DIR
print_status "Working directory: $APP_DIR"

# Update system packages
print_status "Updating system packages..."
apt-get update -y

# Install required system packages
print_status "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    git \
    curl \
    wget \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    certbot \
    python3-certbot-nginx

# Install Chrome
print_status "Installing Google Chrome..."
if ! command -v google-chrome &> /dev/null; then
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    apt-get install -y ./google-chrome-stable_current_amd64.deb || true
    rm -f google-chrome-stable_current_amd64.deb
else
    print_status "Chrome already installed"
fi

# Install ChromeDriver
print_status "Installing ChromeDriver..."
if ! command -v chromedriver &> /dev/null; then
    CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION%%.*}")
    wget -q "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
    unzip -o chromedriver_linux64.zip
    mv chromedriver /usr/local/bin/
    chmod +x /usr/local/bin/chromedriver
    rm -f chromedriver_linux64.zip
else
    print_status "ChromeDriver already installed"
fi

# Create app user if doesn't exist
if ! id "appuser" &>/dev/null; then
    print_status "Creating application user..."
    useradd -r -s /bin/bash -d $APP_DIR appuser
else
    print_status "appuser already exists"
fi

# Create virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate and install dependencies
print_status "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# Create necessary directories
print_status "Creating application directories..."
mkdir -p instance logs results data static

# Generate secret key
print_status "Setting up configuration..."
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Create production config
cat > instance/config.py << EOF
import os

# Production Configuration
SECRET_KEY = '$SECRET_KEY'
SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/journal_scraper.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False
DEBUG = False
TESTING = False

# Security
SESSION_COOKIE_SECURE = False  # Set to True when using HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# File upload
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
UPLOAD_FOLDER = 'results'
DATA_FOLDER = 'data'
EOF

# Initialize database if doesn't exist
if [ ! -f "instance/journal_scraper.db" ]; then
    print_status "Initializing database..."
    python init_database.py
    
    # Run migration
    if [ -f "migrate_database_simple.py" ]; then
        print_status "Running database migrations..."
        echo "y" | python migrate_database_simple.py || print_warning "Migration may have already run"
    fi
else
    print_status "Database already exists"
    # Try to run migration anyway
    if [ -f "migrate_database_simple.py" ]; then
        echo "y" | python migrate_database_simple.py 2>/dev/null || print_status "Database already up to date"
    fi
fi

# Set permissions
print_status "Setting file permissions..."
chown -R appuser:appuser $APP_DIR
chmod -R 755 $APP_DIR
chmod 600 instance/journal_scraper.db 2>/dev/null || true

# Create systemd service
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

# Configure Nginx
print_status "Configuring Nginx..."
cat > /etc/nginx/sites-available/$SERVICE_NAME << 'EOF'
server {
    listen 80;
    server_name _;

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
ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx config
print_status "Testing Nginx configuration..."
nginx -t

# Configure firewall
print_status "Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
fi

# Start services
print_status "Starting services..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME
systemctl restart nginx

# Wait and check status
sleep 3

PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_EC2_IP")

echo ""
echo "=========================================="
print_status "Deployment completed!"
echo "=========================================="
echo ""
echo "Service Status:"
systemctl is-active $SERVICE_NAME && echo "✓ Application: Running" || echo "✗ Application: Failed"
systemctl is-active nginx && echo "✓ Nginx: Running" || echo "✗ Nginx: Failed"
echo ""
echo "Access your application:"
echo "  http://$PUBLIC_IP"
echo ""
echo "Useful Commands:"
echo "  View logs:        journalctl -u $SERVICE_NAME -f"
echo "  Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  Check status:     sudo systemctl status $SERVICE_NAME"
echo "  Nginx logs:       tail -f /var/log/nginx/error.log"
echo "  App logs:         tail -f $APP_DIR/logs/error.log"
echo ""
echo "Default admin credentials (if just created):"
echo "  Username: admin"
echo "  Password: admin123"
echo "  ⚠ CHANGE THIS PASSWORD IMMEDIATELY!"
echo "=========================================="
