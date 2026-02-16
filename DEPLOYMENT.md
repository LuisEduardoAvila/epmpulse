# EPMPulse Production Deployment Guide

Complete guide for deploying EPMPulse in a production environment.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Installation Steps](#3-installation-steps)
4. [Systemd Service Configuration](#4-systemd-service-configuration)
5. [Nginx Reverse Proxy](#5-nginx-reverse-proxy)
6. [SSL Certificate Lets Encrypt](#6-ssl-certificate-lets-encrypt)
7. [Configuration](#7-configuration)
8. [Testing](#8-testing)
9. [Backup Strategy](#9-backup-strategy)
10. [Monitoring](#10-monitoring)
11. [Troubleshooting](#11-troubleshooting)
12. [Security Hardening](#12-security-hardening)

---

## 1. Prerequisites

### 1.1 Python Requirements

- **Python 3.11+** required
- **pip** 23.0+ recommended
- **virtualenv** or **python3-venv** package

```bash
# Check Python version
python3 --version  # Must be 3.11 or higher

# Install venv if missing
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
```

### 1.2 Oracle EPM Cloud Access

Required credentials from Oracle Cloud Console:

| Credential | Description | Where to Find |
|------------|-------------|---------------|
| `EPM_CLIENT_ID` | OAuth Client ID | Oracle Cloud IAM > Applications |
| `EPM_CLIENT_SECRET` | OAuth Client Secret | Oracle Cloud IAM > Applications |
| `EPM_TOKEN_URL` | OAuth Token Endpoint | Oracle Cloud Identity Domain |

**OAuth Scope Required:** `urn:opc:epm`

### 1.3 Slack Workspace Requirements

- Slack workspace with **Canvas** enabled
- Slack App with permissions:
  - `canvas:write`
  - `canvas:read`
  - `chat:write`
  - `channels:read`

### 1.4 Server Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| Disk | 10 GB | 50 GB SSD |
| Network | 100 Mbps | 1 Gbps |

### 1.5 Network Requirements

#### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 22 | TCP | SSH access |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS API endpoint |
| 18800 | TCP | EPMPulse internal (localhost only) |

#### Firewall Rules

```bash
# UFW configuration
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'

# Enable firewall
sudo ufw --force enable
```

#### Outbound Access

EPMPulse requires outbound HTTPS (TCP/443) to the following services:

**Slack API:**
- Hosts: `*.slack.com`, `slack.com`
- **Important:** Slack operates on AWS and does **not** publish fixed IP ranges
- Options for firewall rules:
  1. **Recommended:** Allow outbound to `slack.com:443` (domain-based)
  2. **Alternative:** Allow all outbound HTTPS (if strict firewall required)
  3. **AWS IP Ranges:** Download AWS IP ranges and allow all (complex, changes frequently)

**Oracle EPM Cloud:**
- Hosts: `*.oraclecloud.com`, `*.oracle.com`
- **OCI IP Ranges:** Oracle publishes IP ranges at:
  ```
  https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json
  ```

##### Key OCI IP Ranges by Region

| Region | CIDR Range | Tag |
|--------|-----------|-----|
| **US East (Ashburn)** | `129.213.0.0/20` | OCI |
| **US West (Phoenix)** | `129.146.0.0/20` | OCI |
| **US West (San Jose)** | `146.235.192.0/19` | OCI |
| **UK South (London)** | `132.145.224.0/19` | OCI |
| **EU Frankfurt** | `129.159.192.0/19` | OCI |
| **EU Amsterdam** | `132.145.0.0/20` | OCI |
| **Australia (Sydney)** | `129.148.160.0/20` | OCI |
| **Brazil (São Paulo)** | `144.22.64.0/18` | OCI |
| **Canada (Toronto)** | `140.238.128.0/19` | OCI |
| **Japan (Tokyo)** | `132.145.224.0/20` | OCI |

##### Oracle Services Network (OSN) Ranges

For Oracle EPM Cloud, you need OSN ranges:

| Region | CIDR Range | Services |
|--------|-----------|----------|
| **US East (Ashburn)** | `134.70.24.0/21` | OSN, Object Storage |
| **US West (Phoenix)** | `134.70.8.0/21` | OSN, Object Storage |
| **UK South (London)** | `140.91.32.0/22` | OSN |
| **EU Frankfurt** | `134.70.32.0/22` | OSN, Object Storage |
| **Brazil (São Paulo)** | `134.70.84.0/22` | OSN, Object Storage |

##### Dynamic IP Range Script

Create a script to fetch current OCI ranges:

```bash
#!/bin/bash
# /opt/epmpulse/update-firewall.sh

# Fetch OCI IP ranges
curl -s https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json -o /tmp/oci_ips.json

# Extract OSN ranges for your region (example: us-ashburn-1)
OSN_IPS=$(jq -r '.regions[] | select(.region=="us-ashburn-1") | .cidrs[] | select(.tags | contains(["OSN"])) | .cidr' /tmp/oci_ips.json)

# Add to UFW
for ip in $OSN_IPS; do
    sudo ufw allow out to $ip port 443 proto tcp
    sudo ufw allow out to $ip port 443 proto tcp
    sudo ufw allow in from $ip to any port 443 proto tcp
done

echo "Updated firewall rules for OCI OSN ranges"
```

##### Complete UFW Configuration

```bash
#!/bin/bash
# Complete firewall setup for EPMPulse

# Reset UFW
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change port if using custom)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (via Nginx)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Deny direct EPMPulse access (must go through Nginx)
sudo ufw deny 18800/tcp

# Allow outbound to Slack (if domain-based not possible)
# Note: Slack uses AWS - no fixed IPs available
# Allow all outbound HTTPS (required for Slack)
sudo ufw allow out 443/tcp

# Allow outbound to Oracle EPM (specific IPs if known)
# Example for us-ashburn-1 OSN ranges:
sudo ufw allow out to 134.70.24.0/21 port 443
sudo ufw allow out to 134.70.32.0/22 port 443

# Enable firewall
sudo ufw --force enable

# Check status
sudo ufw status verbose
```

##### iptables Alternative

If using iptables directly:

```bash
# Flush existing rules
sudo iptables -F
sudo iptables -X

# Default policies
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT ACCEPT

# Allow loopback
sudo iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow SSH
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow localhost access to EPMPulse
sudo iptables -A INPUT -p tcp -s 127.0.0.1 --dport 18800 -j ACCEPT

# Save rules
sudo iptables-save > /etc/iptables/rules.v4
```

##### Corporate Firewall Configuration

If behind a corporate firewall, request these openings:

**Outbound (EPMPulse Server → Internet):**

| Destination | Port | Protocol | Purpose |
|-------------|------|----------|---------|
| `*.slack.com` | 443 | TCP | Slack Canvas API |
| `slack.com` | 443 | TCP | Slack OAuth |
| `*.oraclecloud.com` | 443 | TCP | EPM Cloud API |
| `*.identity.oraclecloud.com` | 443 | TCP | Oracle Identity (OAuth) |
| `*.oracle.com` | 443 | TCP | Oracle documentation/updates |

**Inbound (Internet → EPMPulse Server):**

| Source | Port | Protocol | Purpose |
|--------|------|----------|---------|
| Any | 80 | TCP | HTTP redirect |
| Any | 443 | TCP | HTTPS API |
| Corporate VPN | 22 | TCP | SSH management |

**Note on Slack IPs:** Slack runs on AWS and does not publish fixed egress IP ranges. If your corporate firewall requires IP whitelisting:
1. Use domain-based rules if possible
2. Monitor AWS IP ranges at https://ip-ranges.amazonaws.com/ip-ranges.json
3. Allow all HTTPS outbound for Slack functionality
- `letsencrypt.org:443` - Certificate validation (if using Certbot)

---

## 2. Environment Setup

### 2.1 Create Environment File

Create `/opt/epmpulse/.env`:

```bash
# ============================================================================
# EPMPULSE CORE CONFIGURATION
# ============================================================================

# API Security (generate with: openssl rand -hex 32)
EPMPULSE_API_KEY="your_secure_64_character_api_key_here"

# Environment
EPMPULSE_ENV="production"
EPMPULSE_DEBUG="false"
EPMPULSE_HOST="127.0.0.1"
EPMPULSE_PORT="18800"

# Logging
EPMPULSE_LOG_LEVEL="INFO"
EPMPULSE_LOG_FORMAT="json"
EPMPULSE_LOG_FILE="/var/log/epmpulse/epmpulse.log"

# Data Directory
EPMPULSE_DATA_DIR="/opt/epmpulse/data"
EPMPULSE_APPS_CONFIG="/opt/epmpulse/config/apps.json"

# ============================================================================
# SLACK CONFIGURATION
# ============================================================================

# Slack Bot Token (from Slack App OAuth & Permissions)
SLACK_BOT_TOKEN="xoxb-your-bot-token-here"

# Channel IDs and Canvas IDs (see Configuration section below)
SLACK_MAIN_CHANNEL_ID="C0123456789"
SLACK_MAIN_CANVAS_ID="F0123456789"

# Optional: Separate ARCS configuration
SLACK_ARCS_CHANNEL_ID="C9876543210"
SLACK_ARCS_CANVAS_ID="F9876543210"

# ============================================================================
# ORACLE EPM CONFIGURATION (Optional - for pull mode)
# ============================================================================

# OAuth credentials from Oracle IAM
EPM_TOKEN_URL="https://idcs-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.identity.oraclecloud.com/oauth2/v1/token"
EPM_CLIENT_ID="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
EPM_CLIENT_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ============================================================================
# RATE LIMITING (Optional overrides)
# ============================================================================

EPMPULSE_RATE_LIMIT_POST="60 per minute"
EPMPULSE_RATE_LIMIT_GET="100 per minute"
```

### 2.2 Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EPMPULSE_API_KEY` | Yes | - | API authentication key |
| `SLACK_BOT_TOKEN` | Yes | - | Slack Bot OAuth token |
| `SLACK_MAIN_CHANNEL_ID` | Yes | - | Primary Slack channel ID |
| `SLACK_MAIN_CANVAS_ID` | Yes | - | Slack Canvas ID for display |
| `SLACK_ARCS_CHANNEL_ID` | No | - | ARCS-specific channel |
| `SLACK_ARCS_CANVAS_ID` | No | - | ARCS Canvas ID |
| `EPMPULSE_HOST` | No | `0.0.0.0` | Bind address |
| `EPMPULSE_PORT` | No | `18800` | Internal port |
| `EPMPULSE_ENV` | No | `development` | Environment name |
| `EPMPULSE_LOG_LEVEL` | No | `INFO` | Logging level |
| `EPMPULSE_DATA_DIR` | No | `data` | Data directory path |
| `EPM_TOKEN_URL` | No | - | Oracle OAuth endpoint |
| `EPM_CLIENT_ID` | No | - | Oracle OAuth client ID |
| `EPM_CLIENT_SECRET` | No | - | Oracle OAuth secret |

---

## 3. Installation Steps

### 3.1 System User Setup

```bash
# Create dedicated user
sudo useradd -r -s /bin/false -d /opt/epmpulse epmpulse

# Create directories
sudo mkdir -p /opt/epmpulse
sudo mkdir -p /opt/epmpulse/data/backups
sudo mkdir -p /opt/epmpulse/config
sudo mkdir -p /var/log/epmpulse

# Set permissions
sudo chown -R epmpulse:epmpulse /opt/epmpulse
sudo chmod 750 /opt/epmpulse
```

### 3.2 Option A: Virtual Environment Installation

```bash
# Clone repository
cd /opt
git clone https://github.com/your-org/epm-dashboard.git epmpulse

# Create virtual environment
cd /opt/epmpulse
sudo -u epmpulse python3 -m venv venv

# Activate and install dependencies
sudo -u epmpulse bash -c "source venv/bin/activate && pip install -r requirements.txt"

# Copy and update configuration
sudo cp config/apps.json.example config/apps.json
sudo nano config/apps.json  # Edit with your settings

# Set ownership
sudo chown -R epmpulse:epmpulse /opt/epmpulse
```

### 3.3 Option B: Docker Installation

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create user
RUN useradd -r -s /bin/false -m epmpulse

# Set workdir
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=epmpulse:epmpulse . .

# Create data directory
RUN mkdir -p data/backups && chown -R epmpulse:epmpulse data

# Switch to non-root user
USER epmpulse

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:18800/health')" || exit 1

# Expose port
EXPOSE 18800

# Start command
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:18800", "--access-logfile", "-", "--error-logfile", "-", "src.app:create_app()"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  epmpulse:
    build: .
    container_name: epmpulse
    restart: unless-stopped
    
    environment:
      - EPMPULSE_API_KEY=${EPMPULSE_API_KEY}
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
      - SLACK_MAIN_CHANNEL_ID=${SLACK_MAIN_CHANNEL_ID}
      - SLACK_MAIN_CANVAS_ID=${SLACK_MAIN_CANVAS_ID}
      - EPMPULSE_ENV=production
      - EPMPULSE_LOG_LEVEL=INFO
      
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ./logs:/var/log/epmpulse
      
    ports:
      - "127.0.0.1:18800:18800"
      
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:18800/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 5s
```

```bash
# Deploy with Docker Compose
sudo mkdir -p /opt/epmpulse
cd /opt/epmpulse

# Copy docker-compose.yml and .env
sudo cp /path/to/docker-compose.yml .
sudo cp /path/to/.env .

# Start service
sudo docker-compose up -d

# Check status
sudo docker-compose ps
sudo docker-compose logs -f
```

---

## 4. Systemd Service Configuration

### 4.1 Create Service File

Create `/etc/systemd/system/epmpulse.service`:

```ini
[Unit]
Description=EPMPulse - EPM Job Status Dashboard
Documentation=https://github.com/your-org/epm-dashboard
After=network.target
Wants=network.target

[Service]
Type=simple
User=epmpulse
Group=epmpulse
WorkingDirectory=/opt/epmpulse

# Load environment variables
Environment="PATH=/opt/epmpulse/venv/bin"
EnvironmentFile=/opt/epmpulse/.env

# Start command
ExecStart=/opt/epmpulse/venv/bin/gunicorn \
    -w 4 \
    -b 127.0.0.1:18800 \
    --access-logfile /var/log/epmpulse/access.log \
    --error-logfile /var/log/epmpulse/error.log \
    --log-level info \
    --timeout 30 \
    --keep-alive 2 \
    "src.app:create_app()"

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/epmpulse/data /var/log/epmpulse
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true

[Install]
WantedBy=multi-user.target
```

### 4.2 Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service at boot
sudo systemctl enable epmpulse

# Start service
sudo systemctl start epmpulse

# Check status
sudo systemctl status epmpulse

# View logs
sudo journalctl -u epmpulse -f
```

### 4.3 Service Commands Reference

```bash
# Start/stop/restart
sudo systemctl start epmpulse
sudo systemctl stop epmpulse
sudo systemctl restart epmpulse

# Check status
sudo systemctl status epmpulse
sudo systemctl is-active epmpulse

# View logs
sudo journalctl -u epmpulse
sudo journalctl -u epmpulse --since "1 hour ago"
sudo journalctl -u epmpulse -f  # Follow

# Reload after config changes
sudo systemctl reload epmpulse
```

---

## 5. Nginx Reverse Proxy

### 5.1 Install Nginx

```bash
sudo apt-get update
sudo apt-get install -y nginx

# Enable and start
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 5.2 Create Nginx Configuration

Create `/etc/nginx/sites-available/epmpulse`:

```nginx
upstream epmpulse {
    server 127.0.0.1:18800;
    keepalive 32;
}

# Rate limiting zone
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;

server {
    listen 80;
    server_name epmpulse.yourdomain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name epmpulse.yourdomain.com;

    # SSL certificates (from Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/epmpulse.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/epmpulse.yourdomain.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logs
    access_log /var/log/nginx/epmpulse_access.log;
    error_log /var/log/nginx/epmpulse_error.log;

    # API endpoints with rate limiting
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_req_status 429;
        
        proxy_pass http://epmpulse;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        # Buffer settings
        proxy_buffering off;
        proxy_request_buffering off;
        
        # Max body size (16KB for status updates)
        client_max_body_size 16k;
    }

    # Health check (no rate limiting)
    location /health {
        proxy_pass http://epmpulse;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
    }
}
```

### 5.3 Enable Site

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/epmpulse /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## 6. SSL Certificate (Let's Encrypt)

### 6.1 Install Certbot

```bash
# Install Certbot
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Or via snap (recommended)
sudo snap install core
sudo snap refresh core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

### 6.2 Obtain Certificate

```bash
# Option 1: Automatic Nginx configuration
sudo certbot --nginx -d epmpulse.yourdomain.com

# Option 2: Manual with standalone (if Nginx not running)
sudo certbot certonly --standalone -d epmpulse.yourdomain.com

# Follow prompts:
# - Enter email
# - Accept terms
# - Choose whether to share email
# - Select redirect (recommended)
```

### 6.3 Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Certbot installs a systemd timer automatically
# Verify it's active
sudo systemctl list-timers | grep certbot

# Manual renewal (if needed)
sudo certbot renew

# Force renewal
sudo certbot renew --force-renewal
```

### 6.4 Certificate Paths

After issuance, certificates are located at:

```
/etc/letsencrypt/live/epmpulse.yourdomain.com/
├── cert.pem          # Server certificate
├── chain.pem         # Intermediate certificates
├── fullchain.pem     # cert.pem + chain.pem
└── privkey.pem       # Private key
```

---

## 7. Configuration

### 7.1 Finding Slack Channel IDs

1. Open Slack in web browser
2. Navigate to the channel
3. Look at the URL: `https://yourworkspace.slack.com/archives/C0123456789`
4. Channel ID is the part after `/archives/` (e.g., `C0123456789`)

**Alternative method:**

```bash
# Using Slack API
export SLACK_BOT_TOKEN="xoxb-your-token"
curl -s https://slack.com/api/conversations.list \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" | \
  jq '.channels[] | {name: .name, id: .id}'
```

### 7.2 Finding Canvas IDs

1. Open the Canvas in Slack
2. Click the three dots menu (⋯) → "Copy link"
3. Link format: `https://yourworkspace.slack.com/docs/F0123456789`
4. Canvas ID is the part after `/docs/` (e.g., `F0123456789`)

### 7.3 Getting EPM OAuth Credentials

1. **Login to Oracle Cloud Console**
   - Navigate to Identity & Security → Identity → Applications

2. **Create Confidential Application**
   - Name: `EPMPulse Integration`
   - Type: `Confidential Application`

3. **Configure OAuth**
   - Grant type: `Client Credentials`
   - Scope: Add `urn:opc:epm`

4. **Save credentials:**
   - Client ID (displayed after creation)
   - Client Secret (shown once - save immediately)

5. **Get Token URL:**
   - Navigate to Identity → Domain
   - Find Token Endpoint (format: `https://idcs-xxx.identity.oraclecloud.com/oauth2/v1/token`)

### 7.4 Creating Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it `EPMPulse`
4. Navigate to **OAuth & Permissions**
5. Add scopes:
   - `canvas:write`
   - `canvas:read`
   - `chat:write`
   - `channels:read`
6. Install to workspace
7. Copy **Bot User OAuth Token** (starts with `xoxb-`)

---

## 8. Testing

### 8.1 Health Check

```bash
# Local health check
curl http://localhost:18800/health

# Expected response:
# {"status": "healthy"}

# Via Nginx/HTTPS
curl https://epmpulse.yourdomain.com/health
```

### 8.2 API Test Calls

```bash
# Set your API key
export API_KEY="your_api_key_here"
export BASE_URL="https://epmpulse.yourdomain.com"

# Test status update
curl -X POST "$BASE_URL/api/v1/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "app": "Planning",
    "domain": "Actual",
    "status": "Loading",
    "job_id": "TEST_001"
  }'

# Test batch update
curl -X POST "$BASE_URL/api/v1/status/batch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "updates": [
      {"app": "Planning", "domain": "Actual", "status": "OK"},
      {"app": "FCCS", "domain": "Consolidation", "status": "Warning"}
    ]
  }'

# Test get all statuses
curl "$BASE_URL/api/v1/status" \
  -H "Authorization: Bearer $API_KEY"

# Test canvas sync
curl -X POST "$BASE_URL/api/v1/canvas/sync" \
  -H "Authorization: Bearer $API_KEY"
```

### 8.3 Automated Test Script

Create `/opt/epmpulse/scripts/test_deployment.sh`:

```bash
#!/bin/bash
# Deployment test script

set -e

API_KEY="${EPMPULSE_API_KEY:?Set EPMPULSE_API_KEY}"
BASE_URL="${EPMPULSE_URL:-https://epmpulse.yourdomain.com}"

echo "Testing EPMPulse deployment..."
echo "URL: $BASE_URL"

# Health check
echo -n "Health check... "
response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$response" = "200" ]; then
    echo "OK"
else
    echo "FAILED (HTTP $response)"
    exit 1
fi

# API authentication test
echo -n "API authentication... "
response=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $API_KEY" \
  "$BASE_URL/api/v1/status")
if [ "$response" = "200" ]; then
    echo "OK"
else
    echo "FAILED (HTTP $response)"
    exit 1
fi

# Test status update
echo -n "Status update... "
response=$(curl -s -X POST "$BASE_URL/api/v1/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"app":"Planning","domain":"Actual","status":"Loading","job_id":"TEST"}' \
  -w "%{http_code}")
if [ "$response" = "200" ]; then
    echo "OK"
else
    echo "FAILED (HTTP $response)"
    exit 1
fi

echo ""
echo "All tests passed!"
```

```bash
# Run tests
chmod +x /opt/epmpulse/scripts/test_deployment.sh
sudo -u epmpulse /opt/epmpulse/scripts/test_deployment.sh
```

---

## 9. Backup Strategy

### 9.1 Daily Backup Script

Create `/opt/epmpulse/scripts/backup.sh`:

```bash
#!/bin/bash
# EPMPulse daily backup script

set -e

# Configuration
BACKUP_DIR="/opt/epmpulse/data/backups"
DATA_DIR="/opt/epmpulse/data"
CONFIG_DIR="/opt/epmpulse/config"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="epmpulse_backup_${DATE}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Backup data files
if [ -d "$DATA_DIR" ]; then
    cp -r "$DATA_DIR" "$TEMP_DIR/"
fi

# Backup configuration
if [ -d "$CONFIG_DIR" ]; then
    cp -r "$CONFIG_DIR" "$TEMP_DIR/"
fi

# Backup environment file (sans secrets)
grep -v "SECRET\|KEY\|TOKEN" /opt/epmpulse/.env > "$TEMP_DIR/env.example" 2>/dev/null || true

# Create compressed archive
tar -czf "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" -C "$TEMP_DIR" .

# Set permissions
chown epmpulse:epmpulse "$BACKUP_DIR/${BACKUP_NAME}.tar.gz"
chmod 640 "$BACKUP_DIR/${BACKUP_NAME}.tar.gz"

# Clean old backups
find "$BACKUP_DIR" -name "epmpulse_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Log backup
echo "[$(date)] Backup created: ${BACKUP_NAME}.tar.gz" >> /var/log/epmpulse/backup.log

# Optional: Upload to S3 (uncomment and configure)
# aws s3 cp "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" s3://your-bucket/epmpulse-backups/
```

### 9.2 Restore Script

Create `/opt/epmpulse/scripts/restore.sh`:

```bash
#!/bin/bash
# EPMPulse restore script

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop service
sudo systemctl stop epmpulse

# Create restore timestamp
DATE=$(date +%Y%m%d_%H%M%S)

# Backup current state before restore
sudo tar -czf "/opt/epmpulse/data/backups/pre_restore_${DATE}.tar.gz" -C /opt/epmpulse data config 2>/dev/null || true

# Extract backup
TEMP_DIR=$(mktemp -d)
sudo tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Restore files
sudo cp -r "$TEMP_DIR/data"/* /opt/epmpulse/data/ 2>/dev/null || true
sudo cp -r "$TEMP_DIR/config"/* /opt/epmpulse/config/ 2>/dev/null || true

# Set permissions
sudo chown -R epmpulse:epmpulse /opt/epmpulse

# Cleanup
rm -rf "$TEMP_DIR"

# Start service
sudo systemctl start epmpulse

echo "Restore completed from: $BACKUP_FILE"
echo "Previous state saved to: /opt/epmpulse/data/backups/pre_restore_${DATE}.tar.gz"
```

### 9.3 Cron Scheduled Backups

```bash
# Edit crontab
sudo crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/epmpulse/scripts/backup.sh >> /var/log/epmpulse/backup_cron.log 2>&1
```

### 9.4 Backup Verification

```bash
# List backups
ls -la /opt/epmpulse/data/backups/

# Test backup integrity
tar -tzf /opt/epmpulse/data/backups/epmpulse_backup_YYYYMMDD_HHMMSS.tar.gz

# Check backup log
tail /var/log/epmpulse/backup.log
```

---

## 10. Monitoring

### 10.1 Log Monitoring

```bash
# Journal logs
sudo journalctl -u epmpulse -f

# Application logs
sudo tail -f /var/log/epmpulse/epmpulse.log

# Nginx logs
sudo tail -f /var/log/nginx/epmpulse_access.log
sudo tail -f /var/log/nginx/epmpulse_error.log
```

### 10.2 Health Check Endpoint

```bash
# Create health check script
cat > /opt/epmpulse/scripts/healthcheck.sh << 'EOF'
#!/bin/bash
URL="https://epmpulse.yourdomain.com/health"
TIMEOUT=5

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$URL")

if [ "$response" = "200" ]; then
    echo "HEALTHY"
    exit 0
else
    echo "UNHEALTHY (HTTP $response)"
    exit 1
fi
EOF

chmod +x /opt/epmpulse/scripts/healthcheck.sh
```

### 10.3 Prometheus Metrics (Optional)

Add to requirements.txt if using Prometheus:
```
prometheus-flask-exporter
```

Configure metrics endpoint in `src/app.py`:
```python
from prometheus_flask_exporter import PrometheusMetrics

metrics = PrometheusMetrics(app)
```

Metrics available at `/metrics`.

### 10.4 Alerting Setup (Uptime Kuma Example)

```bash
# Install Uptime Kuma (Docker)
docker run -d \
  --restart=always \
  -p 3001:3001 \
  -v uptime-kuma:/app/data \
  --name uptime-kuma \
  louislam/uptime-kuma:1

# Configure monitor:
# - Type: HTTP(s)
# - URL: https://epmpulse.yourdomain.com/health
# - Method: GET
# - Expected status: 200
# - Interval: 60s
```

---

## 11. Troubleshooting

### 11.1 Service Won't Start

```bash
# Check logs
sudo journalctl -u epmpulse -n 50

# Validate configuration
sudo -u epmpulse bash -c "cd /opt/epmpulse && source venv/bin/activate && python -c 'from src.config import Config; c = Config.from_env(); print(c.validate())'"

# Check file permissions
ls -la /opt/epmpulse/
ls -la /opt/epmpulse/data/
sudo -u epmpulse touch /opt/epmpulse/data/test  # Should succeed
```

**Common causes:**
- Missing environment variables
- Incorrect permissions on data directory
- Canvas ID contains placeholder
- Port already in use

### 11.2 Canvas Not Updating

```bash
# Check Slack token scopes
curl -s https://slack.com/api/auth.test \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Verify canvas permissions
curl -s "https://slack.com/api/canvases.access.delete" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"canvas_id\":\"$SLACK_MAIN_CANVAS_ID\"}"

# Check canvas exists
curl -s "https://slack.com/api/canvases.info?canvas_id=$SLACK_MAIN_CANVAS_ID" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
```

**Solutions:**
- Reinstall Slack app with required scopes
- Verify canvas ID is correct
- Check bot is member of channel

### 11.3 API Key Authentication Failing

```bash
# Test API key
curl -v "$BASE_URL/api/v1/status" \
  -H "Authorization: Bearer $API_KEY"

# Check for trailing whitespace
echo "$EPMPULSE_API_KEY" | od -c | tail -3
```

**Solutions:**
- Regenerate API key: `openssl rand -hex 32`
- Update `.env` and restart service
- Check for invisible characters in key

### 11.4 High Memory Usage

```bash
# Check memory usage
sudo systemctl status epmpulse
ps aux | grep gunicorn

# Reduce workers in service file
# Change: -w 4 → -w 2
sudo systemctl edit epmpulse
sudo systemctl restart epmpulse
```

### 11.5 Database Lock Errors

```bash
# Remove stale lock files
sudo -u epmpulse rm -f /opt/epmpulse/data/*.lock

# Check for zombie processes
sudo lsof /opt/epmpulse/data/apps_status.lock

# Restart service
sudo systemctl restart epmpulse
```

### 11.6 SSL Certificate Issues

```bash
# Test certificate
openssl s_client -connect epmpulse.yourdomain.com:443 -servername epmpulse.yourdomain.com

# Check expiration
echo | openssl s_client -servername epmpulse.yourdomain.com -connect epmpulse.yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates

# Force renew
sudo certbot renew --force-renewal
```

---

## Appendix B: OCI-Specific Firewall Configuration

When deploying EPMPulse on Oracle Cloud Infrastructure (OCI), you can use OCI's native security controls instead of host-based firewalls.

### OCI Network Security Groups (Recommended)

Network Security Groups (NSGs) are the preferred way to secure EPMPulse in OCI. They act as virtual firewalls attached to VNICs (network interfaces).

#### Create NSG for EPMPulse

**Using OCI Console:**

1. Navigate to **Networking** → **Virtual Cloud Networks** → Your VCN
2. Click **Network Security Groups** → **Create NSG**
3. Name: `epmpulse-servers`
4. Add the following security rules:

**Ingress Rules (Inbound):**

| Source Type | Source | IP Protocol | Port | Description |
|-------------|--------|-------------|------|-------------|
| CIDR | 0.0.0.0/0 | TCP | 80 | HTTP (redirects to HTTPS) |
| CIDR | 0.0.0.0/0 | TCP | 443 | HTTPS API |
| CIDR | 10.0.0.0/16 | TCP | 22 | SSH (from VCN only) |

**Note:** Replace `10.0.0.0/16` with your VCN CIDR block.

**Egress Rules (Outbound):**

| Destination Type | Destination | IP Protocol | Port | Description |
|-----------------|-------------|-------------|------|-------------|
| CIDR | 0.0.0.0/0 | TCP | 443 | HTTPS (for Slack, OCI, etc.) |
| CIDR | 0.0.0.0/0 | TCP | 53 | DNS (UDP also) |
| CIDR | 0.0.0.0/0 | UDP | 53 | DNS |

**Note:** If your organization requires strict firewall rules, use the region-specific CIDR ranges below instead of `0.0.0.0/0`.

#### Using OCI CLI

```bash
#!/bin/bash
# Create NSG via OCI CLI

# Set compartment OCID
COMPARTMENT_OCID="ocid1.compartment.oc1..aaaa..."
VCN_OCID="ocid1.vcn.oc1.eu-frankfurt-1.aaaa..."

# Create NSG
NSG_OCID=$(oci network nsg create \
    --compartment-id "$COMPARTMENT_OCID" \
    --vcn-id "$VCN_OCID" \
    --display-name "epmpulse-servers" \
    --wait-for-state AVAILABLE \
    --query 'data.id' \
    --raw-output)

echo "Created NSG: $NSG_OCID"

# Add ingress rule: HTTPS (443)
oci network nsg rules add \
    --nsg-id "$NSG_OCID" \
    --direction INGRESS \
    --protocol 6 \
    --source-type CIDR_BLOCK \
    --source "0.0.0.0/0" \
    --tcp-options "destination-port-range={min=443,max=443}"

# Add ingress rule: HTTP (80)
oci network nsg rules add \
    --nsg-id "$NSG_OCID" \
    --direction INGRESS \
    --protocol 6 \
    --source-type CIDR_BLOCK \
    --source "0.0.0.0/0" \
    --tcp-options "destination-port-range={min=80,max=80}"

# Add ingress rule: SSH (22) - restrict to VCN only
oci network nsg rules add \
    --nsg-id "$NSG_OCID" \
    --direction INGRESS \
    --protocol 6 \
    --source-type CIDR_BLOCK \
    --source "10.0.0.0/16" \
    --tcp-options "destination-port-range={min=22,max=22}"

echo "NSG configured successfully!"
```

#### Apply NSG to Instance

**During instance creation (CLI):**
```bash
oci compute instance launch \
    --compartment-id "$COMPARTMENT_OCID" \
    --nsg-ids '["'$NSG_OCID'"]' \
    # ... other parameters
```

**Add to existing instance:**
```bash
# Get VNIC OCID
VNIC_OCID=$(oci compute vnic-attachment list \
    --compartment-id "$COMPARTMENT_OCID" \
    --instance-id "ocid1.instance.oc1.eu-frankfurt-1.aaaa..." \
    --query 'data[0]."vnic-id"' \
    --raw-output)

# Update VNIC to attach NSG
oci network vnic update \
    --vnic-id "$VNIC_OCID" \
    --nsg-ids '["'$NSG_OCID'"]' \
    --force
```

### Region-Specific CIDR Rules for OCI

If your EPMPulse server runs in **eu-frankfurt-1** and connects to EPM also hosted in Frankfurt, you can restrict egress rules to the Frankfurt OSN CIDR ranges listed above.

### Frankfurt Region (eu-frankfurt-1) IP Ranges

**OCI CIDR Ranges for Frankfurt:**

| CIDR | Tag | Purpose |
|------|-----|---------|
| `92.4.240.0/20` | OSN | Oracle Services Network |
| `92.5.240.0/21` | OSN | Oracle Services Network |
| `92.5.248.0/22` | OSN | Oracle Services Network |
| `130.61.0.128/25` | OSN | Oracle Services Network |
| `130.61.2.128/25` | OSN | Oracle Services Network |
| `130.61.4.128/25` | OSN | Oracle Services Network |
| `134.70.40.0/21` | OSN, OBJECT_STORAGE | Oracle Services Network |
| `134.70.48.0/22` | OSN, OBJECT_STORAGE | Oracle Services Network |
| `138.1.0.0/22` | OSN | Oracle Services Network |
| `138.1.40.0/21` | OSN | Oracle Services Network |
| `138.1.64.0/22` | OSN | Oracle Services Network |
| `138.1.108.0/25` | OSN | Oracle Services Network |
| `140.91.16.0/22` | OSN | Oracle Services Network |
| `140.91.20.0/23` | OSN | Oracle Services Network |
| `147.154.128.0/19` | OSN | Oracle Services Network |
| `147.154.160.0/20` | OSN | Oracle Services Network |
| `147.154.176.0/21` | OSN | Oracle Services Network |
| `147.154.184.0/22` | OSN | Oracle Services Network |
| `147.154.189.128/25` | OSN | Oracle Services Network |

**OCI CIDR Ranges for Amsterdam (eu-amsterdam-1):**

| CIDR | Tag | Purpose |
|------|-----|---------|
| `141.144.160.0/20` | OCI | VCN addresses |
| `141.144.176.0/21` | OCI | VCN addresses |
| `141.147.16.0/20` | OCI | VCN addresses |
| `141.147.32.0/21` | OCI | VCN addresses |
| `132.145.0.0/20` | OCI | VCN addresses |
| `132.145.16.0/21` | OCI | VCN addresses |
| `134.70.112.0/22` | OSN | Oracle Services Network |
| `140.91.52.0/23` | OSN | Oracle Services Network |
| `140.204.28.128/25` | OSN | Oracle Services Network |
| `192.29.48.0/22` | OSN | Oracle Services Network |
| `192.29.52.0/21` | OSN | Oracle Services Network |
| `192.29.128.0/23` | OSN | Oracle Services Network |
| `192.29.130.0/24` | OSN | Oracle Services Network |
| `192.29.156.0/23` | OSN | Oracle Services Network |
| `192.29.158.0/22` | OSN | Oracle Services Network, Object Storage |

**Update script for OCI CLI:**

```bash
#!/bin/bash
# Add Amsterdam region egress rules

NSG_OCID="ocid1.networksecuritygroup.oc1.eu-frankfurt-1.xxxx"

# OSN ranges (for EPM Cloud access in Frankfurt)
OSN_CIDRS=(
    "92.4.240.0/20"
    "92.5.240.0/21"
    "92.5.248.0/22"
    "130.61.0.128/25"
    "130.61.2.128/25"
    "130.61.4.128/25"
    "134.70.40.0/21"
    "134.70.48.0/22"
    "138.1.0.0/22"
    "138.1.40.0/21"
    "138.1.64.0/22"
    "138.1.108.0/25"
    "140.91.16.0/22"
    "140.91.20.0/23"
    "147.154.128.0/19"
    "147.154.160.0/20"
    "147.154.176.0/21"
    "147.154.184.0/22"
    "147.154.189.128/25"
)

# Add rules for each OSN CIDR
for cidr in "${OSN_CIDRS[@]}"; do
    oci network nsg rules add \
        --nsg-id "$NSG_OCID" \
        --direction EGRESS \
        --protocol 6 \
        --destination-type CIDR_BLOCK \
        --destination "$cidr" \
        --tcp-options "destination-port-range={min=443,max=443}"
    echo "Added rule for $cidr"
done

echo "Frankfurt region rules configured!"
```

### Alternative: OCI Security Lists

Security Lists are the traditional firewall rules at the subnet level. Use NSGs instead if possible, but if you need Security Lists:

**Using OCI Console:**

1. Navigate to **Networking** → **Virtual Cloud Networks** → Your VCN
2. Click **Security Lists**
3. Select the subnet's security list or create new
4. Add the following rules:

**Ingress Rules:**

| Source Type | Source CIDR | IP Protocol | Port Range | Action |
|-------------|-------------|-------------|------------|--------|
| CIDR | 0.0.0.0/0 | TCP | 443 | Allow |
| CIDR | 0.0.0.0/0 | TCP | 80 | Allow |
| CIDR | 10.0.0.0/16 | TCP | 22 | Allow |

**Egress Rules:**

| Destination Type | Destination CIDR | IP Protocol | Port Range | Action |
|-----------------|-------------------|-------------|------------|--------|
| CIDR | 0.0.0.0/0 | TCP | 443 | Allow |
| CIDR | 0.0.0.0/0 | UDP | 53 | Allow |

### OCI Instance Configurations

#### Shape Recommendations

| Usage | Shape | OCPUs | Memory | Disk |
|-------|-------|-------|--------|------|
| Small (testing) | VM.Standard.E4.Flex | 2 | 8 GB | 50 GB |
| Medium (production) | VM.Standard.E4.Flex | 4 | 16 GB | 100 GB |
| Large (high traffic) | VM.Standard.E4.Flex | 8 | 32 GB | 200 GB |

**OCI CLI to create instance:**

```bash
oci compute instance launch \
    --availability-domain "eu-frankfurt-1-AD-1" \
    --compartment-id "$COMPARTMENT_OCID" \
    --image-id "ocid1.image.oc1.eu-frankfurt-1.aaaa..." \
    --shape "VM.Standard.E4.Flex" \
    --shape-config '{"ocpus":4,"memoryInGBs":16}' \
    --subnet-id "ocid1.subnet.oc1.eu-frankfurt-1.aaaa..." \
    --assign-public-ip true \
    --nsg-ids '["ocid1.networksecuritygroup.oc1.eu-frankfurt-1.xxxx"]' \
    --display-name "epmpulse-prod" \
    --wait-for-state RUNNING
```

#### Boot Volume Encryption

Enable encryption for data protection:

```bash
oci compute boot-volume create \
    --compartment-id "$COMPARTMENT_OCID" \
    --availability-domain "eu-frankfurt-1-AD-1" \
    --source-boot-volume-id "$SOURCE_BOOT_VOLUME_OCID" \
    --encryption-in-transit-type "FULL_ENCRYPTION" \
    --kms-key-id "$VAULT_KEY_OCID"
```

### OCI-Specific Troubleshooting

**Issue: Cannot access EPMPulse from internet**

1. Check NSG rules allow port 443
2. Verify subnet has public IP assigned
3. Check Internet Gateway (IGW) is attached to VCN
4. Verify route table has route to IGW

```bash
# Check instance public IP
oci compute instance list-vnics \
    --instance-id "ocid1.instance.oc1.eu-frankfurt-1.xxxx" \
    --query 'data[0]."public-ip"'

# Check NSG rules
oci network nsg rules list \
    --nsg-id "$NSG_OCID" \
    --query 'data[].{"direction":direction,"protocol":protocol,"source":source,"destination":destination}'
```

**Issue: EPMPulse cannot reach Slack**

1. NSG egress rules must allow HTTPS (443)
2. Check if using strict CIDR rules - Slack requires `0.0.0.0/0` for HTTPS
3. Verify Internet Gateway is attached

**Issue: EPMPulse cannot reach Oracle EPM**

1. Verify egress rules include OSN CIDR ranges
2. Check if EPM instance is in same region (eu-frankfurt-1)
3. Test connectivity:

```bash
# From EPMPulse server
curl -v https://idcs-xxx.identity.oraclecloud.com
```

### Best Practices for OCI

1. **Use NSGs over Security Lists** - NSGs provide better granularity and can be attached to specific instances
2. **Enable Cloud Guard** - For security monitoring and threat detection
3. **Use Vault for secrets** - Store `EPMPULSE_API_KEY` and tokens in OCI Vault, not in instance metadata
4. **Enable VCN Flow Logs** - For network troubleshooting and security auditing
5. **Use Service Gateway** - For private access to OCI services without internet
6. **Enable OS Management** - For automated security patching

---

## 12. Security Hardening

### 12.1 File Permissions

```bash
# Set secure permissions on .env
sudo chmod 640 /opt/epmpulse/.env
sudo chown epmpulse:epmpulse /opt/epmpulse/.env

# Protect data directory
sudo chmod 750 /opt/epmpulse/data
sudo chown -R epmpulse:epmpulse /opt/epmpulse/data

# Protect config
sudo chmod 750 /opt/epmpulse/config
sudo chmod 640 /opt/epmpulse/config/*.json

# Secure logs
sudo chmod 755 /var/log/epmpulse
sudo chown epmpulse:adm /var/log/epmpulse
```

### 12.2 Firewall Configuration

```bash
# UFW rules
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'

# IP-based restrictions (optional)
# Allow only specific IPs to API
# sudo ufw allow from 192.168.1.0/24 to any port 443

sudo ufw --force enable
```

### 12.3 Fail2ban Integration

```bash
# Install fail2ban
sudo apt-get install -y fail2ban

# Create filter
cat > /etc/fail2ban/filter.d/epmpulse.conf << 'EOF'
[Definition]
failregex = ^.*"POST /api/v1/status.*" 401.*$
            ^.*"GET /api/v1/status.*" 401.*$
ignoreregex =
EOF

# Create jail
cat > /etc/fail2ban/jail.d/epmpulse.conf << 'EOF'
[epmpulse]
enabled = true
port = http,https
filter = epmpulse
logpath = /var/log/nginx/epmpulse_access.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

# Restart fail2ban
sudo systemctl restart fail2ban
```

### 12.4 API Key Rotation

```bash
#!/bin/bash
# Rotate API key

# Generate new key
NEW_KEY=$(openssl rand -hex 32)
echo "New API key: $NEW_KEY"

# Update .env
sudo sed -i "s/^EPMPULSE_API_KEY=.*/EPMPULSE_API_KEY=\"$NEW_KEY\"/" /opt/epmpulse/.env

# Reload service (graceful)
sudo systemctl reload epmpulse

# Old key is valid until all clients update
echo "Update your EPM Groovy rules with the new key"
```

### 12.5 Security Checklist

- [ ] API key generated with `openssl rand -hex 32` (minimum)
- [ ] `.env` file has permissions 640
- [ ] Service runs as non-root user (`epmpulse`)
- [ ] Data directory is not world-readable
- [ ] SSL certificate is valid and not expired
- [ ] Firewall only allows ports 80, 443, 22
- [ ] Fail2ban is installed and configured
- [ ] Nginx version is hidden (`server_tokens off`)
- [ ] Security headers are configured
- [ ] Logs are rotated (logrotate configured)
- [ ] Backups are encrypted (if offsite)
- [ ] Slack token has minimum required scopes only

---

## Appendix: Quick Reference Commands

```bash
# Status checks
systemctl status epmpulse
journalctl -u epmpulse -f
docker-compose ps

# Restart
systemctl restart epmpulse
docker-compose restart

# Logs
tail -f /var/log/epmpulse/epmpulse.log
nginx -t && nginx -s reload

# Backup
/opt/epmpulse/scripts/backup.sh
ls -la /opt/epmpulse/data/backups/

# Update
cd /opt/epmpulse && git pull
source venv/bin/activate && pip install -r requirements.txt
systemctl restart epmpulse
```

---

## Support

For issues and questions:
- Documentation: [GitHub Wiki](https://github.com/your-org/epm-dashboard)
- Issues: [GitHub Issues](https://github.com/your-org/epm-dashboard/issues)
- Slack: `#epm-support` channel

**Emergency contacts:**
- Infrastructure: infrastructure@yourcompany.com
- EPM Team: epm-team@yourcompany.com
