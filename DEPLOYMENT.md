# EPMPulse Deployment Guide

Production deployment documentation for EPMPulse EPM Job Status Dashboard.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Installation Steps](#3-installation-steps)
4. [Systemd Service Configuration](#4-systemd-service-configuration)
5. [Nginx Reverse Proxy](#5-nginx-reverse-proxy)
6. [SSL Certificate](#6-ssl-certificate)
7. [Configuration](#7-configuration)
8. [Testing](#8-testing)
9. [Backup Strategy](#9-backup-strategy)
10. [Monitoring](#10-monitoring)
11. [Troubleshooting](#11-troubleshooting)
12. [Security Hardening](#12-security-hardening)

---

## 1. Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| Disk | 10 GB | 50 GB |
| Python | 3.11+ | 3.11+ |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04/24.04 LTS |

### Network Requirements

| Port | Protocol | Purpose | Direction |
|------|----------|---------|-----------|
| 80 | TCP | HTTP (redirect to HTTPS) | Inbound |
| 443 | TCP | HTTPS API | Inbound |
| 18800 | TCP | EPMPulse internal (localhost only) | Localhost |
| 443 | TCP | Oracle EPM Cloud API | Outbound |
| 443 | TCP | Slack API | Outbound |

### External Dependencies

**Oracle EPM Cloud:**
- Active Oracle Cloud Infrastructure (OCI) tenancy
- EPM Cloud service provisioned (Planning, FCCS, or ARCS)
- Service account with REST API access
- OAuth 2.0 confidential application configured

**Slack:**
- Workspace with Canvas feature enabled (paid plans)
- Bot token with following scopes:
  - `canvas:access`
  - `canvas:write`
  - `channels:read`
  - `chat:write`
- App installed to target channels

---

## 2. Environment Setup

Create `/opt/epmpulse/.env`:

```bash
# Application Settings
EPMPULSE_API_KEY=your-secure-random-key-here-change-in-production
EPMPULSE_ENV=production
EPMPULSE_HOST=127.0.0.1
EPMPULSE_PORT=18800

# Logging
EPMPULSE_LOG_LEVEL=INFO
EPMPULSE_LOG_FORMAT=json

# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token-from-slack
SLACK_MAIN_CHANNEL_ID=C0123456789
SLACK_MAIN_CANVAS_ID=Fxxxxxxxxxxxxxxxx
SLACK_ARCS_CHANNEL_ID=C9876543210
SLACK_ARCS_CANVAS_ID=Fyyyyyyyyyyyyyyyy

# EPM OAuth Configuration
EPM_TOKEN_URL=https://idcs-xxx.identity.oraclecloud.com/oauth2/v1/token
EPM_CLIENT_ID=your-confidential-app-client-id
EPM_CLIENT_SECRET=your-confidential-app-client-secret
```

### Generate Secure API Key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Environment File Permissions

```bash
chmod 600 /opt/epmpulse/.env
chown epmpulse:epmpulse /opt/epmpulse/.env
```

---

## 3. Installation Steps

### Option A: Virtual Environment (Recommended)

```bash
# Clone repository
cd /opt
git clone https://github.com/LuisEduardoAvila/epmpulse.git
cd epmpulse

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data directories
mkdir -p data/backups
mkdir -p logs

# Copy configuration
cp config/apps.json.example config/apps.json
# Edit config/apps.json with your settings
```

### Option B: Docker

```bash
# Build image
docker build -t epmpulse:latest .

# Run container
docker run -d \
  --name epmpulse \
  --restart unless-stopped \
  -p 127.0.0.1:18800:18800 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/logs:/app/logs \
  epmpulse:latest

# View logs
docker logs -f epmpulse
```

### Option C: Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  epmpulse:
    build: .
    container_name: epmpulse
    restart: unless-stopped
    ports:
      - "127.0.0.1:18800:18800"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config:ro
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:18800/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Run:
```bash
docker-compose up -d
```

---

## 4. Systemd Service Configuration

Create `/etc/systemd/system/epmpulse.service`:

```ini
[Unit]
Description=EPMPulse EPM Dashboard
After=network.target

[Service]
Type=simple
User=epmpulse
Group=epmpulse
WorkingDirectory=/opt/epmpulse
EnvironmentFile=/opt/epmpulse/.env

ExecStart=/opt/epmpulse/venv/bin/gunicorn \
    -w 4 \
    -b 127.0.0.1:18800 \
    --timeout 60 \
    --keep-alive 2 \
    --access-logfile /var/log/epmpulse/access.log \
    --error-logfile /var/log/epmpulse/error.log \
    --capture-output \
    --enable-stdio-inheritance \
    "src.app:create_app()"

Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/epmpulse/data /opt/epmpulse/logs /var/log/epmpulse

[Install]
WantedBy=multi-user.target
```

### Setup Commands

```bash
# Create user (no shell access)
sudo useradd -r -s /bin/false epmpulse

# Create directories
sudo mkdir -p /opt/epmpulse /var/log/epmpulse

# Set ownership
sudo chown -R epmpulse:epmpulse /opt/epmpulse /var/log/epmpulse

# Copy application files
sudo cp -r /path/to/epmpulse/* /opt/epmpulse/
sudo chown -R epmpulse:epmpulse /opt/epmpulse

# Set permissions
sudo chmod 750 /opt/epmpulse
sudo chmod 600 /opt/epmpulse/.env
sudo chmod -R 755 /opt/epmpulse/venv

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable epmpulse
sudo systemctl start epmpulse

# Check status
sudo systemctl status epmpulse
```

### Service Management

```bash
# Start/stop/restart
sudo systemctl start epmpulse
sudo systemctl stop epmpulse
sudo systemctl restart epmpulse

# View logs
sudo journalctl -u epmpulse -f
sudo tail -f /var/log/epmpulse/error.log
```

---

## 5. Nginx Reverse Proxy

Create `/etc/nginx/sites-available/epmpulse`:

```nginx
upstream epmpulse {
    server 127.0.0.1:18800;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name epmpulse.yourdomain.com;

    # SSL certificates (from Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logs
    access_log /var/log/nginx/epmpulse-access.log;
    error_log /var/log/nginx/epmpulse-error.log;

    location / {
        proxy_pass http://epmpulse;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        proxy_buffering off;
    }

    location /api/v1/health {
        proxy_pass http://epmpulse;
        access_log off;  # Don't log health checks
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name epmpulse.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/epmpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 6. SSL Certificate

### Using Let's Encrypt (Certbot)

```bash
# Install certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d epmpulse.yourdomain.com

# Auto-renewal is enabled by default
# Test renewal
sudo certbot renew --dry-run
```

### Using Custom Certificate

```bash
# Place certificates
sudo cp your_certificate.crt /etc/ssl/certs/epmpulse.crt
sudo cp your_private.key /etc/ssl/private/epmpulse.key

# Update nginx config with paths
ssl_certificate /etc/ssl/certs/epmpulse.crt;
ssl_certificate_key /etc/ssl/private/epmpulse.key;
```

---

## 7. Configuration

### 7.1 Get Slack Channel IDs

```bash
# Using Slack API
curl -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
     "https://slack.com/api/conversations.list" | jq '.channels[] | {name: .name, id: .id}'
```

Or use Slack web app:
1. Open channel in browser
2. URL shows: `.../archives/C0123456789`
3. Channel ID is `C0123456789`

### 7.2 Get Canvas IDs

Create canvas first, then get ID:

```bash
# Create canvas
curl -X POST \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "C0123456789",
    "title": "EPM Job Status Dashboard"
  }' \
  https://slack.com/api/canvases.create
```

Or:
1. Create canvas manually in Slack
2. Open canvas
3. URL shows: `.../canvas/F0123456789`
4. Canvas ID is `F0123456789`

### 7.3 Get EPM OAuth Credentials

1. **Login to OCI Console**
   - Navigate to Identity & Security → OAuth

2. **Create Confidential Application**
   - Name: EPMPulse Integration
   - Allowed Grant Types: Client Credentials
   - Grant the client access to: EPM Cloud Service

3. **Get Credentials**
   - Client ID and Secret shown once
   - Token URL format: `https://idcs-xxx.identity.oraclecloud.com/oauth2/v1/token`

4. **Test Token**
   ```bash
   curl -X POST \
     -u "CLIENT_ID:CLIENT_SECRET" \
     -d "grant_type=client_credentials&scope=urn:opc:epm" \
     "https://idcs-xxx.identity.oraclecloud.com/oauth2/v1/token"
   ```

### 7.4 Update config/apps.json

```bash
# Edit configuration
sudo nano /opt/epmpulse/config/apps.json
```

Replace placeholders with actual values:

```json
{
  "epm": {
    "auth": {
      "type": "oauth",
      "token_url": "${EPM_TOKEN_URL}",
      "client_id": "${EPM_CLIENT_ID}",
      "client_secret": "${EPM_CLIENT_SECRET}",
      "scope": "urn:opc:epm"
    },
    "servers": {
      "planning": {
        "name": "Planning",
        "base_url": "https://planning-epm.fa.us2.oraclecloud.com"
      }
    }
  },
  "apps": {
    "Planning": {
      "display_name": "Planning",
      "domains": ["Actual", "Budget"],
      "server": "planning",
      "channels": ["C0123456789"]
    }
  },
  "channels": {
    "C0123456789": {
      "name": "epm-main",
      "canvas_id": "F0123456789"
    }
  }
}
```

---

## 8. Testing

### 8.1 Health Check

```bash
# Local
curl -H "X-API-Key: $EPMPULSE_API_KEY" \
     http://localhost:18800/api/v1/health

# Via Nginx
curl -H "X-API-Key: $EPMPULSE_API_KEY" \
     https://epmpulse.yourdomain.com/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "state_file": "ok",
    "slack_api": "connected"
  }
}
```

### 8.2 Test Status Update

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EPMPULSE_API_KEY" \
  -d '{
    "app": "Planning",
    "domain": "Actual",
    "status": "Loading",
    "job_id": "TEST_001"
  }' \
  https://epmpulse.yourdomain.com/api/v1/status
```

### 8.3 Verify Slack Update

Check Slack canvas updates within 2-5 seconds.

---

## 9. Backup Strategy

### 9.1 Backup Script

Create `/opt/epmpulse/backup.sh`:

```bash
#!/bin/bash
# EPMPulse Backup Script

BACKUP_DIR="/backup/epmpulse"
DATA_DIR="/opt/epmpulse/data"
CONFIG_DIR="/opt/epmpulse/config"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create backup
tar czf "$BACKUP_DIR/epmpulse-$DATE.tar.gz" \
    -C /opt/epmpulse \
    data config .env

# Remove old backups
find "$BACKUP_DIR" -name "epmpulse-*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Log
echo "[$(date)] Backup completed: epmpulse-$DATE.tar.gz" >> "$BACKUP_DIR/backup.log"
```

Make executable:
```bash
chmod +x /opt/epmpulse/backup.sh
```

### 9.2 Automated Backups

Add to crontab:

```bash
# Daily backup at 2 AM
0 2 * * * /opt/epmpulse/backup.sh

# Weekly backup to remote (if configured)
0 3 * * 0 /opt/epmpulse/backup.sh && rsync -avz /backup/epmpulse/ remote:/backups/
```

### 9.3 Restore from Backup

```bash
# Stop service
sudo systemctl stop epmpulse

# Restore
cd /opt/epmpulse
sudo tar xzf /backup/epmpulse/epmpulse-20260216_020001.tar.gz

# Fix permissions
sudo chown -R epmpulse:epmpulse data config .env

# Start service
sudo systemctl start epmpulse
```

---

## 10. Monitoring

### 10.1 Health Monitoring

```bash
# Add to monitoring system (e.g., UptimeRobot, Pingdom)
curl -f -H "X-API-Key: $EPMPULSE_API_KEY" \
     https://epmpulse.yourdomain.com/api/v1/health || alert
```

### 10.2 Log Monitoring

```bash
# Real-time error monitoring
sudo journalctl -u epmpulse -f | grep -i error

# Check recent errors
sudo journalctl -u epmpulse --since "1 hour ago" | grep -i error

# Access log analysis
sudo awk '{print $1}' /var/log/nginx/epmpulse-access.log | sort | uniq -c | sort -rn | head -10
```

### 10.3 Disk Space

```bash
# Check state file size
du -h /opt/epmpulse/data/apps_status.json

# Monitor data directory
watch -n 60 'du -sh /opt/epmpulse/data'
```

### 10.4 Prometheus Metrics (Optional)

If metrics endpoint implemented:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'epmpulse'
    static_configs:
      - targets: ['localhost:18800']
    metrics_path: '/api/v1/metrics'
```

---

## 11. Troubleshooting

### Common Issues

#### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u epmpulse -n 50
sudo cat /var/log/epmpulse/error.log
```

**Common causes:**
- Missing `.env` file
- Port 18800 already in use: `sudo ss -tlnp | grep 18800`
- Permission issues: `sudo chown -R epmpulse:epmpulse /opt/epmpulse`

**Fix:**
```bash
# Check port usage
sudo lsof -i :18800

# Kill process if needed
sudo kill -9 <PID>
```

#### Canvas Not Updating

**Checklist:**
1. Verify `SLACK_BOT_TOKEN` has `canvas:write` scope
2. Verify canvas ID format (starts with `F`)
3. Check Slack app is added to target channel
4. Review logs for Slack API errors
5. Verify API key is correct

**Test Slack connection:**
```bash
curl -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
     https://slack.com/api/auth.test
```

#### EPM Connection Fails

**Test OAuth token:**
```bash
curl -X POST \
  -u "$EPM_CLIENT_ID:$EPM_CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=urn:opc:epm" \
  "$EPM_TOKEN_URL"
```

**Verify service account:**
- Check OCI Identity Console
- Ensure EPM Cloud Service access granted
- Verify token URL matches your OCI region

#### High Memory Usage

**Symptoms:** Out of memory errors, service killed

**Solutions:**
1. Reduce Gunicorn workers: `-w 2` instead of `-w 4`
2. Check state file size: `du -h data/apps_status.json`
3. Enable log rotation
4. Add swap space if needed

**Monitor memory:**
```bash
sudo systemctl status epmpulse | grep Memory
```

#### 403 Forbidden Errors

**Check API key:**
```bash
# Verify key matches
grep EPMPULSE_API_KEY .env
```

**Check nginx config:**
- Ensure `X-API-Key` header is passed through
- Verify no conflicting auth

#### Slack Rate Limiting

**Symptoms:** `rate_limited` errors in logs

**Solution:**
- EPMPulse has built-in debouncing (2s minimum)
- If still hitting limits, increase `min_update_interval`
- Check Slack API usage dashboard

---

## 12. Security Hardening

### 12.1 File Permissions

```bash
# Application files
sudo chmod 750 /opt/epmpulse
sudo chmod 600 /opt/epmpulse/.env
sudo chmod 644 /opt/epmpulse/config/apps.json
sudo chmod 750 /opt/epmpulse/data
sudo chmod 600 /opt/epmpulse/data/*

# Log files
sudo chmod 755 /var/log/epmpulse
sudo chmod 644 /var/log/epmpulse/*.log
```

### 12.2 Firewall (UFW)

```bash
# Allow SSH (don't lock yourself out!)
sudo ufw allow ssh

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Deny direct access to EPMPulse
sudo ufw deny 18800/tcp

# Enable firewall
sudo ufw enable
```

Verify:
```bash
sudo ufw status
```

Expected output:
```
To                         Action      From
--                         ------      ----
SSH                        ALLOW       Anywhere
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
18800/tcp                  DENY        Anywhere
```

### 12.3 API Key Rotation

**Generate new key:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Update service:**
```bash
# Edit .env
sudo nano /opt/epmpulse/.env

# Restart service
sudo systemctl restart epmpulse
```

**Update integrations:**
- Update Groovy templates
- Update ODI Python scripts
- Update monitoring checks

### 12.4 Fail2Ban (Optional)

```bash
# Install
sudo apt install fail2ban

# Create config
sudo tee /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[epmpulse]
enabled = true
port = http,https
filter = epmpulse
logpath = /var/log/nginx/epmpulse-error.log
maxretry = 3
bantime = 1h
EOF

# Create filter
sudo tee /etc/fail2ban/filter.d/epmpulse.conf << 'EOF'
[Definition]
failregex = ^.*401.*client <HOST>.*$
            ^.*403.*client <HOST>.*$
ignoreregex =
EOF

# Restart
sudo systemctl restart fail2ban
```

### 12.5 Security Checklist

- [ ] API key changed from default
- [ ] `.env` file has 600 permissions
- [ ] Firewall blocks port 18800 from external
- [ ] SSL certificate is valid
- [ ] No secrets in logs
- [ ] Automatic backups configured
- [ ] Fail2Ban installed (optional)
- [ ] Regular security updates: `sudo apt update && sudo apt upgrade`

---

## Quick Reference

### Service Commands
```bash
sudo systemctl {start|stop|restart|status} epmpulse
sudo journalctl -u epmpulse -f
```

### Test Commands
```bash
# Health
curl -H "X-API-Key: $KEY" https://epmpulse.yourdomain.com/api/v1/health

# Update status
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"app":"Planning","domain":"Actual","status":"OK"}' \
     https://epmpulse.yourdomain.com/api/v1/status
```

### Backup & Restore
```bash
# Manual backup
sudo /opt/epmpulse/backup.sh

# Restore
sudo systemctl stop epmpulse
sudo tar xzf /backup/epmpulse/epmpulse-xxx.tar.gz -C /opt/epmpulse
sudo chown -R epmpulse:epmpulse /opt/epmpulse
sudo systemctl start epmpulse
```

---

## Support

For issues not covered in this guide:
1. Check logs: `sudo journalctl -u epmpulse -n 100`
2. Review ARCHITECTURE.md for technical details
3. Check CODE_REVIEW.md for known issues
4. Open issue in GitHub repository

**Version:** This guide reflects EPMPulse v1.0.0
