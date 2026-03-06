#!/bin/bash

################################################################################
# Initial EC2 Setup Script
# Run this ONCE when setting up a new EC2 instance
################################################################################

set -e

echo "=========================================="
echo "EC2 Initial Setup for Journal Scraper"
echo "=========================================="
echo ""

# Configuration - UPDATE THESE
GIT_REPO_URL="https://github.com/YOUR_USERNAME/YOUR_REPO.git"  # UPDATE THIS
APP_DIR="/var/www/journal-scraper"
ADMIN_EMAIL="admin@email.com"  # For SSL cert notifications

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root or with sudo"
    exit 1
fi

# Get Git repository URL
if [ "$GIT_REPO_URL" == "https://github.com/YOUR_USERNAME/YOUR_REPO.git" ]; then
    read -p "Enter your Git repository URL: " GIT_REPO_URL
    if [ -z "$GIT_REPO_URL" ]; then
        print_error "Git repository URL is required"
        exit 1
    fi
fi

print_status "Starting EC2 initial setup..."

# Update system
print_status "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install required packages
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

# Install Chrome and ChromeDriver
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

# Create application user
if ! id "appuser" &>/dev/null; then
    print_status "Creating application user..."
    useradd -r -s /bin/bash -d $APP_DIR appuser
fi

# Create application directory
print_status "Creating application directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# Clone repository
print_status "Cloning repository..."
git clone $GIT_REPO_URL .

# Create virtual environment
print_status "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# Create necessary directories
print_status "Creating application directories..."
mkdir -p instance logs results data

# Generate secret key
print_status "Generating secret key..."
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
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# File upload
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
UPLOAD_FOLDER = 'results'
DATA_FOLDER = 'data'
EOF

# Initialize database
print_status "Initializing database..."
python init_database.py

# Set permissions
print_status "Setting permissions..."
chown -R appuser:appuser $APP_DIR
chmod -R 755 $APP_DIR
chmod 600 instance/journal_scraper.db

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/journal-scraper.service << EOF
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
cat > /etc/nginx/sites-available/journal-scraper << 'EOF'
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
}
EOF

ln -sf /etc/nginx/sites-available/journal-scraper /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx
nginx -t

# Start services
print_status "Starting services..."
systemctl daemon-reload
systemctl enable journal-scraper
systemctl start journal-scraper
systemctl restart nginx

# Configure firewall
print_status "Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Print success message
PUBLIC_IP=$(curl -s ifconfig.me)

echo ""
echo "=========================================="
print_status "Initial setup completed successfully!"
echo "=========================================="
echo ""
echo "Your application is now running at:"
echo "  http://$PUBLIC_IP"
echo ""
echo "Important Next Steps:"
echo "  1. Configure your domain DNS to point to: $PUBLIC_IP"
echo "  2. Setup SSL certificate (see below)"
echo "  3. Configure GitHub Actions secrets"
echo ""
echo "To setup SSL certificate (after DNS is configured):"
echo "  sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com"
echo ""
echo "GitHub Actions Secrets needed:"
echo "  EC2_HOST: $PUBLIC_IP"
echo "  EC2_USER: ubuntu"
echo "  EC2_SSH_KEY: (contents of your .pem file)"
echo ""
echo "Useful Commands:"
echo "  View logs:        journalctl -u journal-scraper -f"
echo "  Restart service:  sudo systemctl restart journal-scraper"
echo "  Check status:     sudo systemctl status journal-scraper"
echo "=========================================="
