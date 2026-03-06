# 🚀 AWS EC2 Deployment Guide for Journal Scraper

Complete guide to deploy your Flask application to AWS EC2 with CI/CD pipeline.

---

## 📋 Prerequisites

Before starting, ensure you have:

- [ ] AWS Account
- [ ] GitHub Account
- [ ] Git installed on your local machine
- [ ] SSH client (Terminal/PowerShell/PuTTY)
- [ ] Domain name (optional, but recommended for SSL)

---

## 🔧 Part 1: Local Git Setup

### Step 1: Initialize Git Repository

```bash
# Navigate to your project directory
cd D:\Tools4PBI\WebScraperApp

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Journal Scraper Application"
```

### Step 2: Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository (e.g., `journal-scraper-app`)
3. **DO NOT** initialize with README, .gitignore, or license (we already have these)
4. Copy the repository URL

### Step 3: Push to GitHub

```bash
# Add remote
git remote add origin https://github.com/YOUR_USERNAME/journal-scraper-app.git

# Push code
git branch -M main
git push -u origin main
```

**✅ Your code is now on GitHub!**

---

## ☁️ Part 2: AWS EC2 Setup

### Step 1: Launch EC2 Instance

1. **Login to AWS Console**
   - Go to https://console.aws.amazon.com/ec2/

2. **Launch Instance**
   - Click "Launch Instance"
   - **Name**: `journal-scraper-prod`
   - **AMI**: Ubuntu Server 22.04 LTS (Free tier eligible)
   - **Instance Type**: `t2.medium` or `t3.medium` (recommended for Selenium)
   - **Key Pair**: 
     - Create new key pair
     - Name: `journal-scraper-key`
     - Type: RSA
     - Format: .pem (for Linux/Mac) or .ppk (for Windows/PuTTY)
     - **DOWNLOAD AND SAVE THIS FILE SECURELY**

3. **Network Settings**
   - Allow SSH (port 22) from your IP
   - Allow HTTP (port 80) from anywhere (0.0.0.0/0)
   - Allow HTTPS (port 443) from anywhere (0.0.0.0/0)

4. **Storage**
   - 20 GB or more (SSD)

5. **Launch Instance**

6. **Get Public IP**
   - Note down the public IP address (e.g., `54.123.45.67`)

### Step 2: Connect to EC2 Instance

**For Linux/Mac:**
```bash
# Set correct permissions for key file
chmod 400 journal-scraper-key.pem

# Connect to instance
ssh -i journal-scraper-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

**For Windows (PowerShell):**
```powershell
# Connect using PowerShell
ssh -i journal-scraper-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

**For Windows (PuTTY):**
1. Convert .pem to .ppk using PuTTYgen
2. Use PuTTY to connect with .ppk file

---

## 🛠️ Part 3: Deploy Application

### Step 1: Initial Setup (Run Once)

```bash
# On your EC2 instance, download setup script
wget https://raw.githubusercontent.com/YOUR_USERNAME/journal-scraper-app/main/setup_ec2.sh

# Make it executable
chmod +x setup_ec2.sh

# Run setup (you'll be prompted for your Git repo URL)
sudo ./setup_ec2.sh
```

**The script will:**
- Install all dependencies (Python, Nginx, Chrome, ChromeDriver)
- Clone your repository
- Create virtual environment
- Initialize database
- Setup systemd service
- Configure Nginx reverse proxy
- Start the application

**This takes 5-10 minutes. Get coffee! ☕**

### Step 2: Verify Deployment

```bash
# Check if service is running
sudo systemctl status journal-scraper

# View logs
journalctl -u journal-scraper -f

# Test locally
curl http://localhost:5000
```

**Open in browser:** `http://YOUR_EC2_PUBLIC_IP`

**✅ Your app should be live!**

---

## 🔄 Part 4: Setup CI/CD Pipeline

### Step 1: Configure GitHub Secrets

1. Go to your GitHub repository
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click "New repository secret"

Add these secrets:

**EC2_HOST**
- Value: Your EC2 public IP (e.g., `54.123.45.67`)

**EC2_USER**
- Value: `ubuntu`

**EC2_SSH_KEY**
- Value: Contents of your `.pem` file
- Open `journal-scraper-key.pem` in text editor
- Copy entire content including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`

### Step 2: Test CI/CD Pipeline

```bash
# Make a small change
echo "# Updated" >> README.md

# Commit and push
git add .
git commit -m "Test CI/CD pipeline"
git push
```

**Watch the deployment:**
1. Go to GitHub repository
2. Click **Actions** tab
3. You'll see the deployment workflow running
4. Click on it to see progress

**✅ Automatic deployment working!**

---

## 🔒 Part 5: Setup SSL Certificate (Optional but Recommended)

### Prerequisites
- Domain name pointing to your EC2 IP address

### Steps

```bash
# SSH into your EC2 instance
ssh -i journal-scraper-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

# Install SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Follow prompts
# - Enter email address
# - Agree to terms
# - Choose to redirect HTTP to HTTPS

# Test automatic renewal
sudo certbot renew --dry-run
```

**✅ Your site is now secure with HTTPS!**

---

## 📊 Part 6: Monitoring & Management

### View Application Logs
```bash
# Real-time application logs
journalctl -u journal-scraper -f

# Last 100 lines
journalctl -u journal-scraper -n 100

# Nginx access logs
tail -f /var/log/nginx/access.log

# Nginx error logs
tail -f /var/log/nginx/error.log

# Application logs
tail -f /var/www/journal-scraper/logs/error.log
```

### Manage Service
```bash
# Restart application
sudo systemctl restart journal-scraper

# Stop application
sudo systemctl stop journal-scraper

# Start application
sudo systemctl start journal-scraper

# Check status
sudo systemctl status journal-scraper

# Restart Nginx
sudo systemctl restart nginx
```

### Manual Deployment (Without CI/CD)
```bash
# SSH to server
ssh -i journal-scraper-key.pem ubuntu@YOUR_EC2_IP

# Navigate to app directory
cd /var/www/journal-scraper

# Pull latest changes
sudo -u appuser git pull

# Activate virtual environment
source venv/bin/activate

# Update dependencies (if requirements.txt changed)
pip install -r requirements.txt

# Run migrations (if any)
python migrate_database_simple.py

# Restart service
sudo systemctl restart journal-scraper
```

---

## 🔧 Troubleshooting

### Application Not Starting

```bash
# Check service status
sudo systemctl status journal-scraper

# View detailed logs
journalctl -u journal-scraper -xe

# Check if port 5000 is in use
sudo netstat -tulpn | grep 5000

# Test Gunicorn manually
cd /var/www/journal-scraper
source venv/bin/activate
gunicorn --bind 127.0.0.1:5000 app:app
```

### Database Issues

```bash
# Check database file permissions
ls -la /var/www/journal-scraper/instance/journal_scraper.db

# Fix permissions if needed
sudo chown appuser:appuser /var/www/journal-scraper/instance/journal_scraper.db
sudo chmod 644 /var/www/journal-scraper/instance/journal_scraper.db
```

### Nginx Issues

```bash
# Test Nginx configuration
sudo nginx -t

# View Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Restart Nginx
sudo systemctl restart nginx
```

### Out of Memory Issues

```bash
# Create swap file (if not exists)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### ChromeDriver Issues

```bash
# Check Chrome version
google-chrome --version

# Check ChromeDriver version
chromedriver --version

# Reinstall ChromeDriver if needed
cd /tmp
CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION%%.*}")
wget "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip"
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
```

---

## 📈 Performance Optimization

### 1. Increase Gunicorn Workers

Edit: `/etc/systemd/system/journal-scraper.service`

```ini
# Change from --workers 4 to match: (2 x CPU cores) + 1
ExecStart=/var/www/journal-scraper/venv/bin/gunicorn --workers 8 ...
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart journal-scraper
```

### 2. Enable Nginx Caching

Edit: `/etc/nginx/sites-available/journal-scraper`

Add inside `server` block:
```nginx
location /static {
    alias /var/www/journal-scraper/static;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

Reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Database Optimization

```bash
# Regular backup
sudo -u appuser cp /var/www/journal-scraper/instance/journal_scraper.db \
  /var/www/journal-scraper/instance/journal_scraper.db.backup

# Vacuum database (optimize)
sqlite3 /var/www/journal-scraper/instance/journal_scraper.db "VACUUM;"
```

---

## 🔐 Security Best Practices

### 1. Update Regularly
```bash
# Auto-update security patches
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get autoremove -y
```

### 2. Change Default SSH Port (Optional)
```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Change line: Port 22 → Port 2222
# Restart SSH
sudo systemctl restart sshd

# Update firewall
sudo ufw allow 2222/tcp
sudo ufw delete allow 22/tcp
```

### 3. Disable Root Login
```bash
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no
sudo systemctl restart sshd
```

### 4. Enable Fail2Ban
```bash
sudo apt-get install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 📦 Backup Strategy

### Create Backup Script

```bash
sudo nano /usr/local/bin/backup-journal-scraper.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp /var/www/journal-scraper/instance/journal_scraper.db \
   $BACKUP_DIR/journal_scraper_$DATE.db

# Backup results (if needed)
tar -czf $BACKUP_DIR/results_$DATE.tar.gz \
   /var/www/journal-scraper/results

# Keep only last 7 days
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

Make executable and schedule:
```bash
sudo chmod +x /usr/local/bin/backup-journal-scraper.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-journal-scraper.sh") | crontab -
```

---

## 🎯 Complete Deployment Checklist

- [ ] Git repository created and code pushed
- [ ] EC2 instance launched and accessible
- [ ] Initial setup script executed successfully
- [ ] Application accessible via public IP
- [ ] GitHub Actions secrets configured
- [ ] CI/CD pipeline tested and working
- [ ] SSL certificate installed (if using domain)
- [ ] Admin user created in application
- [ ] Firewall configured
- [ ] Monitoring setup
- [ ] Backup strategy implemented
- [ ] Documentation updated

---

## 🆘 Getting Help

If you encounter issues:

1. **Check logs first**: `journalctl -u journal-scraper -f`
2. **Review Nginx logs**: `/var/log/nginx/error.log`
3. **Test locally**: `curl http://localhost:5000`
4. **Verify permissions**: `ls -la /var/www/journal-scraper`
5. **Check GitHub Actions**: Review failed workflow runs

---

## 📚 Additional Resources

- [AWS EC2 Documentation](https://docs.aws.amazon.com/ec2/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
- [GitHub Actions Documentation](https://docs.github.com/actions)
- [Let's Encrypt / Certbot](https://certbot.eff.org/)

---

**🎉 Congratulations! Your application is now deployed on AWS with automatic CI/CD!**

Every push to the `main` branch will automatically deploy to your EC2 instance.
