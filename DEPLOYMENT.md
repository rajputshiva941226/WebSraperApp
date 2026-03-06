# Deployment Guide - Journal Scraper Web Server

This guide covers deployment options from simple local hosting to production cloud deployment.

## Table of Contents
1. [Local Development](#local-development)
2. [Production Deployment](#production-deployment)
3. [Cloud Deployment](#cloud-deployment)
4. [Docker Deployment](#docker-deployment)
5. [Monitoring & Maintenance](#monitoring--maintenance)

---

## Local Development

### Quick Start (Recommended for testing)

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```bash
start.bat
```

### Manual Setup

```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate virtual environment
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the server
python web_server.py
```

The server will be available at `http://localhost:5000`

---

## Production Deployment

### Option 1: Simple Production Setup with Gunicorn

**1. Install Gunicorn:**
```bash
pip install gunicorn
```

**2. Update config.py:**
```python
SERVER_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': False,  # IMPORTANT: Set to False
}
```

**3. Run with Gunicorn:**
```bash
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 web_server:app
```

Parameters explained:
- `-w 4`: Use 4 worker processes
- `-b 0.0.0.0:5000`: Bind to all interfaces on port 5000
- `--timeout 300`: 5-minute timeout for long-running scrapers

**4. Create a systemd service (Linux):**

Create `/etc/systemd/system/journal-scraper.service`:

```ini
[Unit]
Description=Journal Scraper Web Server
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/journal-scraper
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 web_server:app

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable journal-scraper
sudo systemctl start journal-scraper
sudo systemctl status journal-scraper
```

### Option 2: Nginx Reverse Proxy (Recommended)

**1. Install Nginx:**
```bash
sudo apt update
sudo apt install nginx
```

**2. Configure Nginx:**

Create `/etc/nginx/sites-available/journal-scraper`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Change this

    # Max upload size
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running scrapers
        proxy_read_timeout 600;
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
    }

    # Static files
    location /static {
        alias /path/to/journal-scraper/static;
    }
}
```

**3. Enable the site:**
```bash
sudo ln -s /etc/nginx/sites-available/journal-scraper /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

**4. Add SSL with Let's Encrypt:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Cloud Deployment

### AWS EC2 Deployment

**1. Launch EC2 Instance:**
- AMI: Ubuntu 22.04 LTS
- Instance Type: t3.medium (2 vCPU, 4 GB RAM minimum)
- Storage: 30 GB SSD
- Security Group: Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS)

**2. Connect and Setup:**
```bash
# Connect via SSH
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3-pip python3-venv nginx -y

# Install Chrome (for Selenium)
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb -y

# Clone your project
git clone your-repo-url
cd journal-scraper

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Follow production setup steps above
```

**3. Configure Security:**
```bash
# Setup firewall
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### DigitalOcean Droplet

Similar to AWS EC2, but simpler:

**1. Create Droplet:**
- Ubuntu 22.04
- 2 GB RAM / 1 vCPU (Basic plan)
- Choose datacenter region

**2. Follow AWS setup steps above**

### Google Cloud Platform (GCP)

**1. Create VM Instance:**
```bash
gcloud compute instances create journal-scraper \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB
```

**2. Follow AWS setup steps above**

---

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy application
COPY . .

# Create results directory
RUN mkdir -p results

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "300", "web_server:app"]
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./results:/app/results
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
```

### Build and Run

```bash
# Build image
docker build -t journal-scraper .

# Run container
docker run -d -p 5000:5000 -v $(pwd)/results:/app/results journal-scraper

# Or use docker-compose
docker-compose up -d
```

---

## Monitoring & Maintenance

### Logging

**1. Application Logs:**
```bash
# View systemd logs
sudo journalctl -u journal-scraper -f

# View Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

**2. Application-level logging:**

Update `config.py`:
```python
LOGGING_CONFIG = {
    'level': 'INFO',
    'file': 'scraper_server.log',
}
```

### Backup Strategy

**1. Automated backups:**

Create backup script `backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backup/journal-scraper"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup results
tar -czf $BACKUP_DIR/results_$DATE.tar.gz results/

# Keep only last 7 days
find $BACKUP_DIR -name "results_*.tar.gz" -mtime +7 -delete
```

**2. Add to crontab:**
```bash
# Run backup daily at 2 AM
0 2 * * * /path/to/backup.sh
```

### Performance Monitoring

**1. Install monitoring tools:**
```bash
sudo apt install htop iotop
```

**2. Monitor resources:**
```bash
# CPU and memory
htop

# Disk I/O
sudo iotop

# Disk space
df -h
```

### Health Checks

Use the `/health` endpoint:

```bash
# Check if server is running
curl http://localhost:5000/health
```

**Setup automated health checks:**

Create `health_check.sh`:
```bash
#!/bin/bash
RESPONSE=$(curl -s http://localhost:5000/health)
if [[ $RESPONSE == *"healthy"* ]]; then
    echo "OK: Server is healthy"
    exit 0
else
    echo "ERROR: Server is not responding"
    # Restart service
    sudo systemctl restart journal-scraper
    exit 1
fi
```

Add to crontab (check every 5 minutes):
```bash
*/5 * * * * /path/to/health_check.sh
```

---

## Security Checklist

- [ ] Change `SECRET_KEY` in config.py to a random string
- [ ] Set `debug=False` in production
- [ ] Enable HTTPS with SSL certificate
- [ ] Configure firewall (UFW or Security Groups)
- [ ] Use strong passwords for server access
- [ ] Keep system and packages updated
- [ ] Implement rate limiting for API endpoints
- [ ] Add authentication for sensitive operations
- [ ] Regular backups
- [ ] Monitor logs for suspicious activity

---

## Troubleshooting

### Issue: Chrome/Selenium not working in Docker

**Solution:** Ensure Chrome is properly installed and add these options:
```python
CHROME_OPTIONS = [
    '--headless',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu'
]
```

### Issue: Out of memory errors

**Solution:** 
1. Increase swap space
2. Upgrade server RAM
3. Limit concurrent jobs in config.py

### Issue: Scrapers timing out

**Solution:**
```python
# In config.py
SCRAPER_SETTINGS = {
    'timeout': 600,  # Increase timeout
}
```

### Issue: Permission denied errors

**Solution:**
```bash
# Set proper permissions
sudo chown -R www-data:www-data /path/to/journal-scraper
sudo chmod -R 755 /path/to/journal-scraper
```

---

## Next Steps

1. ✅ Deploy to production server
2. ✅ Configure domain and SSL
3. ✅ Setup monitoring and backups
4. 🔄 Add more scrapers as needed
5. 🔄 Implement user authentication (if needed)
6. 🔄 Add email notifications
7. 🔄 Consider Redis for job queue (for high traffic)

---

For additional support, check the main README.md or contact the development team.
