# EPMPulse Architecture Design & Review

**Document Version:** 1.0  
**Date:** 2026-02-16  
**Status:** Architecture Review Complete  
**Author:** Architecture Review (Subagent)

---

## Executive Summary

EPMPulse is a lightweight status dashboard that bridges Oracle EPM Cloud job execution with Slack Canvas display. The architecture prioritizes **simplicity** (MVP-first), **reliability** (critical EPM jobs), and **maintainability** (team handoff).

**Key Architectural Decisions:**
1. JSON file for state (simple, fast, reliable)
2. Flask API (lightweight, team-familiar)
3. Slack Canvas (persistent, passive display)
4. Simple API key auth (environment-isolated)
5. Optional Oracle AI DB for scale-out

---

## 1. API Design

### 1.1 Endpoints Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EPMPulse API                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  POST   /api/v1/status              Update app/domain status       │
│  POST   /api/v1/status/batch        Batch update (multi-app jobs)  │
│  GET    /api/v1/status              Get all statuses               │
│  GET    /api/v1/status/{app}        Get specific app statuses      │
│  POST   /api/v1/canvas/sync         Force canvas refresh           │
│  GET    /api/v1/health              Health check                   │
│  GET    /api/v1/canvas/preview      Preview canvas JSON            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Detailed API Specification

#### POST /api/v1/status

Update a single app/domain status. Called from Groovy rules or ODI scripts.

**Request:**
```json
{
  "app": "Planning",
  "domain": "Actual",
  "status": "Loading",
  "job_id": "LOAD_20260216_001",
  "message": "Optional message",
  "timestamp": "2026-02-16T14:30:00Z"
}
```

**Request Schema:**
```yaml
StatusUpdateRequest:
  type: object
  required:
    - app
    - status
  properties:
    app:
      type: string
      enum: [Planning, FCCS, ARCS]
      description: Target application
    domain:
      type: string
      description: Domain within app (e.g., "Actual", "Budget", "Consolidation")
      default: "default"
    status:
      type: string
      enum: [Blank, Loading, OK, Warning]
      description: New status
    job_id:
      type: string
      description: Correlation ID from EPM/ODI
    message:
      type: string
      maxLength: 200
      description: Optional context (error message, etc.)
    timestamp:
      type: string
      format: date-time
      description: Event time (defaults to now if omitted)
```

**Response (Success):**
```json
{
  "success": true,
  "updated": {
    "app": "Planning",
    "domain": "Actual",
    "status": "Loading",
    "job_id": "LOAD_20260216_001",
    "updated_at": "2026-02-16T14:30:00Z"
  },
  "canvas_updated": true
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_STATUS",
    "message": "Status must be one of: Blank, Loading, OK, Warning"
  }
}
```

---

#### POST /api/v1/status/batch

Update multiple apps in one call. Used for multi-app pipelines (e.g., Full Load → Planning + FCCS).

**Request:**
```json
{
  "updates": [
    {
      "app": "Planning",
      "domain": "Actual",
      "status": "OK",
      "job_id": "FULL_20260216_001"
    },
    {
      "app": "FCCS",
      "domain": "Consolidation",
      "status": "OK",
      "job_id": "FULL_20260216_001"
    }
  ],
  "job_id": "FULL_20260216_001",
  "timestamp": "2026-02-16T14:35:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "updated_count": 2,
  "updates": [
    {"app": "Planning", "domain": "Actual", "status": "OK"},
    {"app": "FCCS", "domain": "Consolidation", "status": "OK"}
  ],
  "canvas_updated": true
}
```

---

#### GET /api/v1/status

Retrieve all current statuses.

**Response:**
```json
{
  "last_updated": "2026-02-16T14:35:00Z",
  "apps": {
    "Planning": {
      "Actual": {"status": "OK", "job_id": "FULL_001", "updated": "..."},
      "Budget": {"status": "Loading", "job_id": "BUD_002", "updated": "..."},
      "Forecast": {"status": "OK", "job_id": "FULL_001", "updated": "..."}
    },
    "FCCS": {
      "Consolidation": {"status": "OK", "job_id": "FULL_001", "updated": "..."}
    },
    "ARCS": {
      "Reconciliation": {"status": "Warning", "job_id": "ARCS_001", "message": "Timeout", "updated": "..."}
    }
  }
}
```

---

#### GET /api/v1/status/{app}

Retrieve status for a specific app.

**Path Parameters:**
- `app` - Application name (Planning, FCCS, ARCS)

**Response:**
```json
{
  "app": "Planning",
  "domains": {
    "Actual": {"status": "OK", "job_id": "..."},
    "Budget": {"status": "Loading", "job_id": "..."},
    "Forecast": {"status": "OK", "job_id": "..."}
  },
  "last_updated": "2026-02-16T14:35:00Z"
}
```

---

#### POST /api/v1/canvas/sync

Force canvas update (useful after manual state changes or recovery).

**Response:**
```json
{
  "success": true,
  "canvas_id": "F12345678",
  "channel": "C12345678",
  "updated_at": "2026-02-16T14:36:00Z"
}
```

---

#### GET /api/v1/health

Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "state_file": "ok",
    "slack_api": "ok",
    "last_update": "2026-02-16T14:35:00Z"
  }
}
```

---

### 1.3 Authentication

**Approach: Simple API Key**

```
Authorization: Bearer epmpulse_key_<random_32_char_string>
```

**Why simple?**
- Environment separated from OpenClaw
- No OAuth complexity needed
- Single tenant (your team only)
- Easy key rotation

**Implementation:**
```python
from functools import wraps
from flask import request, jsonify
import secrets

API_KEYS = {
    "epm_groovy": "epmpulse_key_xxx...",    # For EPM business rules
    "odi_python": "epmpulse_key_yyy...",    # For ODI scripts
    "admin": "epmpulse_key_zzz..."          # For admin operations
}

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({"error": {"code": "MISSING_AUTH"}}), 401
        
        key = auth[7:]
        if key not in API_KEYS.values():
            return jsonify({"error": {"code": "INVALID_KEY"}}), 403
        
        return f(*args, **kwargs)
    return decorated
```

---

### 1.4 Error Handling

**Error Response Format:**
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

**Error Codes:**

| Code | HTTP | Description |
|------|------|-------------|
| `MISSING_AUTH` | 401 | No Authorization header |
| `INVALID_KEY` | 403 | API key not recognized |
| `INVALID_STATUS` | 400 | Status not in allowed values |
| `INVALID_APP` | 400 | App not in configured list |
| `STATE_ERROR` | 500 | JSON state file read/write error |
| `SLACK_ERROR` | 502 | Slack API call failed |
| `RATE_LIMITED` | 429 | Too many requests |

**Idempotency:**
- Same status update with same job_id is idempotent
- No duplicate logging, no duplicate canvas updates

---

### 1.5 Rate Limiting

**Default Limits:**
- POST /api/v1/status: 60/minute per API key
- POST /api/v1/status/batch: 20/minute per API key
- GET endpoints: 100/minute per IP

**Implementation:**
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute"]
)

@app.route('/api/v1/status', methods=['POST'])
@limiter.limit("60 per minute")
@require_api_key
def update_status():
    ...
```

---

## 2. State Management

### 2.1 JSON Structure

**File:** `data/apps_status.json`

```json
{
  "version": "1.0",
  "last_updated": "2026-02-16T14:35:00Z",
  "metadata": {
    "created": "2026-02-01T00:00:00Z",
    "schema_version": "1.0"
  },
  "apps": {
    "Planning": {
      "display_name": "Planning",
      "channels": ["C_MAIN_CHANNEL"],
      "domains": {
        "Actual": {
          "status": "OK",
          "job_id": "FULL_20260216_001",
          "message": null,
          "updated": "2026-02-16T14:30:00Z",
          "duration_sec": 145
        },
        "Budget": {
          "status": "Loading",
          "job_id": "BUD_20260216_002",
          "message": null,
          "updated": "2026-02-16T14:32:00Z",
          "duration_sec": null
        },
        "Forecast": {
          "status": "OK",
          "job_id": "FULL_20260216_001",
          "message": null,
          "updated": "2026-02-16T14:30:00Z",
          "duration_sec": 145
        }
      }
    },
    "FCCS": {
      "display_name": "FCCS",
      "channels": ["C_MAIN_CHANNEL"],
      "domains": {
        "Consolidation": {
          "status": "OK",
          "job_id": "FULL_20260216_001",
          "message": null,
          "updated": "2026-02-16T14:30:00Z",
          "duration_sec": 145
        }
      }
    },
    "ARCS": {
      "display_name": "ARCS",
      "channels": ["C_ARCS_CHANNEL"],
      "domains": {
        "Reconciliation": {
          "status": "Warning",
          "job_id": "ARCS_20260216_001",
          "message": "Timeout on batch 3",
          "updated": "2026-02-16T14:25:00Z",
          "duration_sec": 892
        }
      }
    }
  },
  "recent_jobs": [
    {
      "job_id": "FULL_20260216_001",
      "apps": ["Planning", "FCCS"],
      "status": "OK",
      "started": "2026-02-16T14:27:35Z",
      "completed": "2026-02-16T14:30:00Z"
    }
  ]
}
```

### 2.2 Concurrent Access Handling

**Challenge:** Multiple EPM jobs may update status simultaneously.

**Solution: File Locking with Atomic Writes**

```python
import fcntl
import json
import tempfile
import os
from pathlib import Path

STATE_FILE = Path("data/apps_status.json")
LOCK_FILE = Path("data/apps_status.lock")

class StateManager:
    def __init__(self, state_file=STATE_FILE):
        self.state_file = state_file
        self._lock = None
    
    def __enter__(self):
        self._lock = open(LOCK_FILE, 'w')
        fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX)
        return self
    
    def __exit__(self, *args):
        if self._lock:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
            self._lock.close()
    
    def read(self) -> dict:
        if not self.state_file.exists():
            return self._default_state()
        with open(self.state_file, 'r') as f:
            return json.load(f)
    
    def write(self, state: dict):
        # Atomic write: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, self.state_file)
        except:
            os.unlink(tmp_path)
            raise
    
    def _default_state(self) -> dict:
        return {
            "version": "1.0",
            "last_updated": None,
            "metadata": {"created": datetime.utcnow().isoformat() + "Z"},
            "apps": {},
            "recent_jobs": []
        }
```

**Usage Pattern:**
```python
# Safe concurrent update
with StateManager() as state:
    state['apps'][app]['domains'][domain] = {
        "status": status,
        "job_id": job_id,
        "updated": datetime.utcnow().isoformat() + "Z"
    }
    state.write(state)  # Atomic write happens here
```

### 2.3 Recovery on Restart

**Startup Routine:**

1. **Verify state file exists** - Create if missing
2. **Validate JSON integrity** - Rebuild if corrupted
3. **Recover "Loading" states** - Jobs interrupted during restart
4. **Sync canvas** - Ensure Slack matches state

```python
def recover_state():
    """Called on API server startup."""
    with StateManager() as sm:
        state = sm.read()
        
        # Check for interrupted jobs (in Loading state)
        loading_jobs = []
        for app_name, app_data in state.get('apps', {}).items():
            for domain_name, domain_data in app_data.get('domains', {}).items():
                if domain_data.get('status') == 'Loading':
                    loading_jobs.append({
                        'app': app_name,
                        'domain': domain_name,
                        'job_id': domain_data.get('job_id')
                    })
        
        if loading_jobs:
            logger.warning(f"Found {len(loading_jobs)} jobs in Loading state on restart")
            # Option 1: Set to Warning (conservative)
            # Option 2: Keep Loading (expect EPM to update)
            # Recommended: Keep Loading with timeout
        
        return state
```

**Stale Loading Recovery:**

```python
STALE_LOADING_TIMEOUT = timedelta(hours=2)

def check_stale_loading(state: dict) -> list:
    """Check for Loading states older than timeout."""
    now = datetime.utcnow()
    stale = []
    
    for app_name, app_data in state.get('apps', {}).items():
        for domain_name, domain_data in app_data.get('domains', {}).items():
            if domain_data.get('status') == 'Loading':
                updated = datetime.fromisoformat(domain_data['updated'].rstrip('Z'))
                if now - updated > STALE_LOADING_TIMEOUT:
                    stale.append((app_name, domain_name))
    
    return stale

# Periodic check (every 5 minutes via scheduler or heartbeat)
```

### 2.4 Configuration Structure

**File:** `config/apps.json`

```json
{
  "apps": {
    "Planning": {
      "display_name": "Planning",
      "domains": ["Actual", "Budget", "Forecast"],
      "channels": ["C12345678"]
    },
    "FCCS": {
      "display_name": "FCCS", 
      "domains": ["Consolidation"],
      "channels": ["C12345678"]
    },
    "ARCS": {
      "display_name": "ARCS",
      "domains": ["Reconciliation"],
      "channels": ["C87654321"]
    }
  },
  "channels": {
    "C12345678": {
      "name": "epm-main",
      "canvas_id": "Fxxxxxxxx"
    },
    "C87654321": {
      "name": "arcs-support",
      "canvas_id": "Fyyyyyyyy"
    }
  }
}
```

---

## 3. Slack Canvas Integration

### 3.1 Canvas Block Structure

**Main Channel Dashboard:**

```
┌────────────────────────────────────────────────────────────────────┐
│ 📊 EPM Status Dashboard                          Last: 14:35 GMT   │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ▸ PLANNING                                                        │
│    ├─ Actual      🟢 OK         Job: FULL_001   (2m 25s ago)       │
│    ├─ Budget      🟡 Loading    Job: BUD_002    (30s ago)           │
│    └─ Forecast    🟢 OK         Job: FULL_001   (2m 25s ago)        │
│                                                                    │
│  ▸ FCCS                                                            │
│    └─ Consolidation  🟢 OK      Job: FULL_001   (2m 25s ago)        │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│  Recent: Full Load (FULL_001) completed 14:30                     │
└────────────────────────────────────────────────────────────────────┘
```

**Canvas JSON Structure:**

```json
{
  "type": "canvas",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "📊 EPM Status Dashboard"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "plain_text",
          "text": "Last updated: 14:35 GMT | "
        },
        {
          "type": "plain_text",
          "text": "🔄 Auto-refresh on job events"
        }
      ]
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*▸ PLANNING*"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "Actual"
        },
        {
          "type": "mrkdwn", 
          "text": "🟢 OK"
        },
        {
          "type": "mrkdwn",
          "text": "_Job: FULL_001 • 2m ago_"
        }
      ]
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "Budget"
        },
        {
          "type": "mrkdwn",
          "text": "🟡 Loading"
        },
        {
          "type": "mrkdwn",
          "text": "_Job: BUD_002 • Started 30s ago_"
        }
      ]
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "Forecast"
        },
        {
          "type": "mrkdwn",
          "text": "🟢 OK"
        },
        {
          "type": "mrkdwn",
          "text": "_Job: FULL_001 • 2m ago_"
        }
      ]
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*▸ FCCS*"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "Consolidation"
        },
        {
          "type": "mrkdwn",
          "text": "🟢 OK"
        },
        {
          "type": "mrkdwn",
          "text": "_Job: FULL_001 • 2m ago_"
        }
      ]
    },
    {
      "type": "divider"
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "_Recent: Full Load (FULL_001) completed at 14:30_"
        }
      ]
    }
  ]
}
```

### 3.2 Status Icons & Colors

| Status | Icon | Color Hint | Description |
|--------|------|------------|-------------|
| Blank | ⚪ | gray | No status yet |
| Loading | 🟡 | yellow | Job in progress |
| OK | 🟢 | green | Completed successfully |
| Warning | 🔴 | red | Failed or errors |

### 3.3 Update Strategy

**Recommendation: Full Replace**

**Why not partial update?**
- Slack Canvas API doesn't support true partial updates
- Easier to reason about state consistency
- Simpler error recovery
- Low frequency updates (not real-time UI)

**Implementation:**

```python
def update_canvas(channel_id: str, canvas_id: str, state: dict):
    """Full canvas update."""
    blocks = build_canvas_blocks(state)
    
    try:
        client.conversations_canvas_edit(
            channel_id=channel_id,
            canvas_id=canvas_id,
            document=blocks
        )
        return True
    except SlackApiError as e:
        logger.error(f"Canvas update failed: {e}")
        return False
```

**Update Triggers:**
1. Any status change (POST /api/v1/status)
2. Manual sync (POST /api/v1/canvas/sync)
3. Startup recovery

### 3.4 Rate Limiting Considerations

**Slack API Limits:**
- `conversations.canvas.edit`: ~1 req/sec per workspace
- Burst allowed, sustained rate matters

**Debouncing Strategy:**

```python
from collections import deque
from datetime import datetime, timedelta

class CanvasUpdateQueue:
    def __init__(self, min_interval_sec=2):
        self.min_interval = timedelta(seconds=min_interval_sec)
        self.last_update = None
        self.pending = False
    
    def request_update(self):
        """Request a canvas update. Returns True if immediate, False if deferred."""
        now = datetime.utcnow()
        
        if self.last_update is None or now - self.last_update > self.min_interval:
            self.last_update = now
            return True  # Execute immediately
        else:
            self.pending = True
            return False  # Defer
    
    def should_update_now(self) -> bool:
        """Check if pending update should execute now."""
        if not self.pending:
            return False
        
        now = datetime.utcnow()
        if now - self.last_update > self.min_interval:
            self.pending = False
            self.last_update = now
            return True
        return False

# Background task checks queue every second
```

### 3.5 Multi-Canvas Support

Each channel may have its own canvas:

```python
class CanvasManager:
    def __init__(self, config: dict, slack_client):
        self.config = config
        self.client = slack_client
        self.canvases = {}  # channel_id -> canvas_id
    
    def update_channel_canvas(self, channel_id: str, state: dict):
        """Update canvas for specific channel."""
        canvas_id = self._get_or_create_canvas(channel_id)
        
        # Filter state for this channel's apps
        channel_apps = self._get_channel_apps(channel_id)
        filtered_state = self._filter_state(state, channel_apps)
        
        blocks = self._build_blocks(filtered_state)
        return self._update(canvas_id, blocks)
    
    def update_all_canvases(self, state: dict):
        """Update all canvases (called after state change)."""
        results = {}
        for channel_id in self.config['channels']:
            results[channel_id] = self.update_channel_canvas(channel_id, state)
        return results
```

---

## 4. Integration Points

### 4.1 Groovy Integration (EPM Native)

**Business Rule Template:**

```groovy
/**
 * EPMPulse Status Update Business Rule
 * Call from data exchange jobs via EPM Job Console
 */

// Configuration (store in EPM Application properties or hardcoded)
String API_URL = "https://epmpulse.yourdomain.com/api/v1/status"
String API_KEY = "epmpulse_key_xxx..."  // Secure credential storage recommended

def updateEPMStatus(String app, String domain, String status, String jobId, String message = null) {
    try {
        // Build JSON payload
        def payload = [
            app: app,
            domain: domain,
            status: status,
            job_id: jobId,
            timestamp: new Date().format("yyyy-MM-dd'T'HH:mm:ss'Z'")
        ]
        
        if (message) {
            payload.message = message
        }
        
        // HTTP POST request
        def connection = new URL(API_URL).openConnection()
        connection.setRequestMethod("POST")
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Authorization", "Bearer ${API_KEY}")
        connection.setDoOutput(true)
        
        // Send payload
        def outputStream = connection.getOutputStream()
        outputStream.write(new groovy.json.JsonBuilder(payload).toString().getBytes("UTF-8"))
        outputStream.close()
        
        // Check response
        def responseCode = connection.getResponseCode()
        if (responseCode >= 200 && responseCode < 300) {
            println "EPMPulse: Status updated successfully"
            return true
        } else {
            println "EPMPulse: Failed with code ${responseCode}"
            return false
        }
    } catch (Exception e) {
        println "EPMPulse Error: ${e.message}"
        return false
    }
}

// Usage examples:

// At job start
updateEPMStatus("Planning", "Actual", "Loading", job.jobId)

// At job completion
updateEPMStatus("Planning", "Actual", "OK", job.jobId)

// On error
updateEPMStatus("Planning", "Actual", "Warning", job.jobId, "Data load failed: ${error}")
```

**Integration Pattern:**

```
EPM Data Exchange Job
    │
    ├── 1. Pre-load step: Groovy rule
    │       └── updateEPMStatus("Planning", "Actual", "Loading", job_id)
    │
    ├── 2. Load data (native EPM)
    │
    └── 3. Post-load step: Groovy rule
            └── if (success) updateEPMStatus("Planning", "Actual", "OK", job_id)
                else updateEPMStatus(..., "Warning", job_id, error)
```

### 4.2 Python Integration (ODI)

**Module Structure:**

```python
# epm_pulse_client.py

import requests
from typing import List, Optional
from datetime import datetime

class EPMPulseClient:
    """
    Client for EPMPulse API.
    Used from ODI Python steps or standalone scripts.
    """
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
    
    def update_status(
        self,
        app: str,
        domain: str,
        status: str,
        job_id: Optional[str] = None,
        message: Optional[str] = None
    ) -> dict:
        """Update single app/domain status."""
        payload = {
            'app': app,
            'domain': domain,
            'status': status,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        if job_id:
            payload['job_id'] = job_id
        if message:
            payload['message'] = message
        
        response = self.session.post(f'{self.base_url}/api/v1/status', json=payload)
        response.raise_for_status()
        return response.json()
    
    def batch_update(
        self,
        updates: List[dict],
        job_id: Optional[str] = None
    ) -> dict:
        """Update multiple apps in one call."""
        payload = {
            'updates': updates,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        if job_id:
            payload['job_id'] = job_id
        
        response = self.session.post(
            f'{self.base_url}/api/v1/status/batch',
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def notify_pipeline_start(
        self,
        apps: List[str],
        domain: str,
        job_id: str
    ) -> dict:
        """Convenience: Mark multiple apps as Loading."""
        updates = [
            {'app': app, 'domain': domain, 'status': 'Loading', 'job_id': job_id}
            for app in apps
        ]
        return self.batch_update(updates, job_id)
    
    def notify_pipeline_complete(
        self,
        apps: List[str],
        domain: str,
        job_id: str,
        success: bool,
        message: Optional[str] = None
    ) -> dict:
        """Convenience: Mark pipeline completion."""
        status = 'OK' if success else 'Warning'
        updates = [
            {
                'app': app,
                'domain': domain,
                'status': status,
                'job_id': job_id,
                'message': message
            }
            for app in apps
        ]
        return self.batch_update(updates, job_id)


# ODI Integration Example

# From ODI Python step:
# Note: ODI passes variables via odiRef or environment

import os
from epm_pulse_client import EPMPulseClient

# Get config from ODI variables or environment
PULSE_URL = os.environ.get('EPMPULSE_URL', 'http://hspi.local:18800')
PULSE_KEY = os.environ.get('EPMPULSE_KEY')

pulse = EPMPulseClient(PULSE_URL, PULSE_KEY)

def on_job_start():
    """Called at pipeline start."""
    job_id = odiRef.getSession('SESS_NAME')  # ODI session name as job ID
    
    pulse.notify_pipeline_start(
        apps=['Planning', 'FCCS'],
        domain='Actual',
        job_id=job_id
    )

def on_job_complete(success: bool, error_msg: str = None):
    """Called at pipeline end."""
    job_id = odiRef.getSession('SESS_NAME')
    
    pulse.notify_pipeline_complete(
        apps=['Planning', 'FCCS'],
        domain='Actual',
        job_id=job_id,
        success=success,
        message=error_msg
    )

# In ODI scenario flow:
# Step 1 (Python): on_job_start()
# Step 2-N: Data flows
# Last Step (Python): on_job_complete(success=True) or on_job_complete(False, error)
```

### 4.3 Error Handling in Integration

**Groovy:**
- Catch exceptions, log but don't fail job
- EPM job success/failure is independent of status update

**Python/ODI:**
- Use try/except around pulse calls
- Log failures but raise only on critical errors
- Add timeout handling

```python
def safe_update_status(pulse: EPMPulseClient, **kwargs):
    """Update status with error handling."""
    try:
        result = pulse.update_status(**kwargs, timeout=5.0)
        log.info(f"EPMPulse updated: {result}")
        return True
    except requests.Timeout:
        log.warning("EPMPulse timeout - status update skipped")
        return False
    except requests.RequestException as e:
        log.error(f"EPMPulse error: {e}")
        return False
```

### 4.4 Pull Mode (Optional Fallback)

**When to Use:** When push notifications from EPM/ODI fail or are unreliable.

**Implementation:**
```python
# EPMPulse can poll EPM job status ( requires job ID stored on trigger )
def check_job_status(job_id: str) -> dict:
    """Poll EPM for job status using job ID."""
    url = f"https://{EPM_SERVER}/epm/rest/v1/jobRuns/{job_id}"
    response = requests.get(url, auth=(USER, PASS), timeout=30)
    return response.json()

# Response includes: status, jobName, descriptiveStatus, details
```

**Critical Limitations:**
- ❌ **Cannot query by job name** - must have job ID
- ✅ Job ID is returned when triggering job via EPM REST API
- Store job ID in EPMPulse when receiving 'Loading' status
- Use for self-healing: if push fails, poll with stored job ID

**Configuration:**
```json
{
  "pull_mode": {
    "enabled": true,
    "poll_interval_seconds": 30,
    "max_poll_duration_minutes": 60,
    "epm_credentials": {
      "server": "planning.oraclecloud.com",
      "user": "service.account",
      "password": "${EPM_PASSWORD}"  // Environment variable
    }
  }
}
```

### 4.5 Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Oracle Cloud Infrastructure                │
│  ┌─────────────────┐        ┌─────────────────┐               │
│  │  EPM Cloud       │        │  ODI             │               │
│  │  (Planning,      │        │  (Data ETL)      │               │
│  │   FCCS, ARCS)    │        │                  │               │
│  │                  │        │                  │               │
│  │  Groovy Rules    │        │  Python Scripts  │               │
│  └────────┬─────────┘        └────────┬─────────┘               │
│           │                           │                         │
│           │    ┌───────────────────┐    │                         │
│           │    │  EPM REST API    │    │                         │
│           │    │  jobRuns/{id}    │    │                         │
│           │    │  (Pull Mode)     │    │                         │
│           │    └───────────────────┘    │                         │
└───────────┼───────────────────────────┼─────────────────────────┘
            │ HTTPS                     │ HTTPS
            │                           │
            └───────────┬───────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  EPMPulse Server (Your Environment)                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Flask API (port 18800)                                 │   │
│  │  - /api/v1/status                                       │   │
│  │  - /api/v1/status/batch                                 │   │
│  │  - /api/v1/canvas/sync                                  │   │
│  └───────────────────────┬─────────────────────────────────┘   │
│                          │                                      │
│  ┌───────────────────────┼─────────────────────────────────┐   │
│  │  State Layer          │                                 │   │
│  │  - apps_status.json (state)                             │   │
│  │  - stores job_id for pull mode                          │   │
│  └───────────────────────┼─────────────────────────────────┘   │
│                          │                                      │
│  ┌───────────────────────┼─────────────────────────────────┐   │
│  │  Slack Integration     │                                 │   │
│  │  - Bolt SDK client                                      │   │
│  │  - Canvas management                                     │   │
│  └───────────────────────┼─────────────────────────────────┘   │
└──────────────────────────┼──────────────────────────────────────┘
                           │
                           │ HTTPS (Slack API)
                           ▼
        ┌──────────────────────────────────────┐
        │  Slack Workspace                    │
        │  - #epm-main (Main Canvas)          │
        │  - #arcs-support (ARCS Canvas)       │
        └──────────────────────────────────────┘
```

---

## 5. Scalability Path

### 5.1 When to Migrate to Oracle AI DB

**Decision Matrix:**

| Factor | Stay with JSON | Migrate to Oracle AI DB |
|--------|---------------|------------------------|
| **Instances** | Single | Multiple (HA, regions) |
| **Query needs** | None | SQL analytics, trends |
| **History depth** | Recent only | Long-term (months) |
| **Team size** | Small team | Large org |
| **Uptime SLA** | Best effort | 99.9%+ |
| **Compliance** | None required | Audit trails, retention |

**Recommended thresholds for migration:**
- More than 10 apps
- Need for historical trend queries
- Multi-instance deployment (HA)
- Compliance requirements for audit

### 5.2 Oracle AI DB Schema

**If migrating from JSON:**

```sql
-- Status table (current state per app/domain)
CREATE TABLE epm_status (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    app_name VARCHAR2(50) NOT NULL,
    domain_name VARCHAR2(50) NOT NULL,
    status VARCHAR2(20) NOT NULL CHECK (status IN ('Blank', 'Loading', 'OK', 'Warning')),
    job_id VARCHAR2(100),
    message VARCHAR2(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
    duration_sec NUMBER,
    CONSTRAINT uk_app_domain UNIQUE (app_name, domain_name)
);

-- Job history table
CREATE TABLE epm_job_history (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_id VARCHAR2(100) NOT NULL,
    job_type VARCHAR2(50),
    apps_affected VARCHAR2(500),  -- JSON array or comma-separated
    status VARCHAR2(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_sec NUMBER,
    error_message VARCHAR2(2000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

-- Status change audit
CREATE TABLE epm_status_audit (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    app_name VARCHAR2(50) NOT NULL,
    domain_name VARCHAR2(50) NOT NULL,
    old_status VARCHAR2(20),
    new_status VARCHAR2(20) NOT NULL,
    job_id VARCHAR2(100),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
    changed_by VARCHAR2(100)
);

-- Indexes
CREATE INDEX idx_status_app ON epm_status(app_name);
CREATE INDEX idx_job_history_job_id ON epm_job_history(job_id);
CREATE INDEX idx_job_history_started ON epm_job_history(started_at);
```

### 5.3 Multi-Instance Architecture

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  EPMPulse #1    │ │  EPMPulse #2    │ │  EPMPulse #3    │
│  (primary)      │ │  (replica)      │ │  (replica)      │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Oracle AI DB   │
                    │  (shared state) │
                    └─────────────────┘
```

**Considerations:**
- Session affinity not needed (stateless API, shared DB)
- Canvas update should be single-writer (use distributed lock or leader election)
- Health checks with DB connectivity test

### 5.4 Performance Targets

| Metric | JSON Mode | Oracle AI DB Mode |
|--------|-----------|-------------------|
| Status update latency | < 50ms | < 200ms |
| Canvas update latency | < 1s | < 1.5s |
| Concurrent updates | 10/sec | 100/sec |
| State query latency | < 10ms | < 50ms |

---

## 6. Risk Assessment

### 6.1 Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| EPM can't reach EPMPulse API | Medium | High | Async with retry; heartbeat check |
| Slack API rate limits | Low | Medium | Debouncing; batch updates |
| JSON file corruption | Low | High | Atomic writes; backups; validation |
| Concurrent update conflicts | Medium | Medium | File locking; idempotent updates |
| API key exposure | Low | High | Secure storage; key rotation |
| Canvas update failure | Medium | Low | Retry logic; manual sync endpoint |
| Server downtime | Medium | High | Monitoring; auto-recovery on restart |
| Config mismatch | Low | Medium | Schema validation; startup checks |

### 6.2 Risk Mitigation Details

#### EPM Reachability

```python
# In Groovy: Retry logic
def updateWithRetry(String app, String domain, String status, String jobId, int retries = 3) {
    for (int i = 0; i < retries; i++) {
        try {
            if (updateEPMStatus(app, domain, status, jobId)) {
                return true
            }
        } catch (Exception e) {
            Thread.sleep(5000)  // Wait 5 seconds
        }
    }
    log.warning("Failed to update EPMPulse after ${retries} attempts")
    return false
}
```

#### State File Backup

```python
# Periodic backup (every hour or on change)
import shutil
from datetime import datetime

def backup_state_file():
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    backup_path = STATE_FILE.parent / 'backups' / f'status_{timestamp}.json'
    shutil.copy2(STATE_FILE, backup_path)
    # Clean old backups (keep last 24)
    clean_old_backups(keep=24)

# On startup: verify state integrity
def validate_state(state: dict) -> bool:
    required_keys = ['version', 'apps']
    for key in required_keys:
        if key not in state:
            return False
    # Validate each app has valid status
    valid_statuses = {'Blank', 'Loading', 'OK', 'Warning'}
    for app_data in state.get('apps', {}).values():
        for domain_data in app_data.get('domains', {}).values():
            if domain_data.get('status') not in valid_statuses:
                return False
    return True
```

#### Monitoring & Alerting

```python
# Health endpoint for monitoring
@app.route('/api/v1/health')
def health():
    checks = {
        'state_file': check_state_file(),
        'slack_api': check_slack_connection(),
        'last_update': get_last_update_time()
    }
    
    all_healthy = all(v == 'ok' for v in checks.values() if v != 'last_update')
    
    return jsonify({
        'status': 'healthy' if all_healthy else 'degraded',
        'checks': checks
    }), 200 if all_healthy else 503

# Alert if no updates in 24 hours (check every hour)
IDLE_THRESHOLD = timedelta(hours=24)

def check_idle_alert():
    state = read_state()
    last = datetime.fromisoformat(state['last_updated'].rstrip('Z'))
    if datetime.utcnow() - last > IDLE_THRESHOLD:
        send_alert("No EPM status updates in 24h - check integration")
```

---

## 7. Implementation Recommendations

### 7.1 MVP Implementation Order

**Week 1-2: Core API**
1. Set up Flask project structure
2. Implement state management (JSON)
3. Build POST /api/v1/status endpoint
4. Add API key authentication
5. Write unit tests

**Week 3: Slack Integration**
6. Create Slack app and bot token
7. Implement Canvas update logic
8. Build canvas block generator
9. Test manual canvas updates

**Week 4: End-to-End**
10. Integrate state → canvas flow
11. Add health endpoint
12. Create Groovy rule template
13. Write Python client module
14. Deploy to server

**Week 5: Polish**
15. Add logging and monitoring
16. Create runbook/documentation
17. Load testing
18. Team handoff

### 7.2 Project Structure

```
epmpulse/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── status.py
│   │   └── canvas.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── state_manager.py
│   │   └── canvas_client.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   └── utils/
│       ├── __init__.py
│       └── auth.py
├── config/
│   ├── apps.json
│   └── settings.yaml
├── data/
│   ├── apps_status.json
│   └── backups/
├── integrations/
│   ├── groovy/
│   │   └── epmpulse_rule.groovy
│   └── python/
│       └── epm_pulse_client.py
├── tests/
│   ├── test_api.py
│   ├── test_state.py
│   └── test_canvas.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

### 7.3 Dependencies

```txt
# requirements.txt
flask>=3.0
flask-limiter>=3.0
slack-sdk>=3.0
requests>=2.0
pydantic>=2.0  # Request validation
gunicorn>=21.0  # Production server
python-dotenv>=1.0  # Environment config
```

### 7.4 Deployment Checklist

- [ ] Server provisioned (your environment)
- [ ] Python 3.11+ installed
- [ ] Slack app created, bot token obtained
- [ ] Canvas created in target channels
- [ ] API keys generated and distributed
- [ ] Config file populated (apps.json)
- [ ] First manual canvas update tested
- [ ] Service running (systemd/supervisor)
- [ ] Monitoring configured (health endpoint)
- [ ] Backups scheduled
- [ ] Documentation complete

---

## 8. API Specification (OpenAPI Format)

```yaml
openapi: 3.1.0
info:
  title: EPMPulse API
  description: EPM Job Status Dashboard API
  version: 1.0.0
  contact:
    name: EPM Team

servers:
  - url: https://epmpulse.yourdomain.com
    description: Production

security:
  - BearerAuth: []

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      description: API key from EPMPulse config

  schemas:
    Status:
      type: string
      enum: [Blank, Loading, OK, Warning]
    
    AppName:
      type: string
      enum: [Planning, FCCS, ARCS]
    
    StatusUpdate:
      type: object
      required:
        - app
        - status
      properties:
        app:
          $ref: '#/components/schemas/AppName'
        domain:
          type: string
          default: default
        status:
          $ref: '#/components/schemas/Status'
        job_id:
          type: string
        message:
          type: string
          maxLength: 200
        timestamp:
          type: string
          format: date-time
    
    BatchStatusUpdate:
      type: object
      required:
        - updates
      properties:
        updates:
          type: array
          items:
            $ref: '#/components/schemas/StatusUpdate'
        job_id:
          type: string
        timestamp:
          type: string
          format: date-time
    
    DomainStatus:
      type: object
      properties:
        status:
          $ref: '#/components/schemas/Status'
        job_id:
          type: string
        message:
          type: string
        updated:
          type: string
          format: date-time
        duration_sec:
          type: integer
    
    AppStatus:
      type: object
      properties:
        display_name:
          type: string
        channels:
          type: array
          items:
            type: string
        domains:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/DomainStatus'
    
    FullStatus:
      type: object
      properties:
        version:
          type: string
        last_updated:
          type: string
          format: date-time
        apps:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/AppStatus'
    
    Error:
      type: object
      properties:
        success:
          type: boolean
          example: false
        error:
          type: object
          properties:
            code:
              type: string
            message:
              type: string
            details:
              type: object

paths:
  /api/v1/status:
    post:
      summary: Update app status
      operationId: updateStatus
      tags: [Status]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/StatusUpdate'
      responses:
        '200':
          description: Status updated successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  updated:
                    $ref: '#/components/schemas/DomainStatus'
                  canvas_updated:
                    type: boolean
        '400':
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '401':
          description: Missing authentication
        '403':
          description: Invalid API key
    
    get:
      summary: Get all statuses
      operationId: getStatuses
      tags: [Status]
      responses:
        '200':
          description: Current status for all apps
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FullStatus'

  /api/v1/status/{app}:
    get:
      summary: Get status for specific app
      operationId: getAppStatus
      tags: [Status]
      parameters:
        - name: app
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Status for specified app
          content:
            application/json:
              schema:
                type: object
                properties:
                  app:
                    type: string
                  domains:
                    type: object
                  last_updated:
                    type: string
                    format: date-time
        '404':
          description: App not found

  /api/v1/status/batch:
    post:
      summary: Batch update multiple apps
      operationId: batchUpdateStatus
      tags: [Status]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BatchStatusUpdate'
      responses:
        '200':
          description: Batch update completed
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  updated_count:
                    type: integer
                  updates:
                    type: array
                    items:
                      type: object
                  canvas_updated:
                    type: boolean

  /api/v1/canvas/sync:
    post:
      summary: Force canvas synchronization
      operationId: syncCanvas
      tags: [Canvas]
      responses:
        '200':
          description: Canvas synced
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  canvas_id:
                    type: string
                  channel:
                    type: string
                  updated_at:
                    type: string
                    format: date-time

  /api/v1/health:
    get:
      summary: Health check
      operationId: healthCheck
      tags: [System]
      security: []
      responses:
        '200':
          description: Service healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [healthy, degraded]
                  checks:
                    type: object
                    properties:
                      state_file:
                        type: string
                      slack_api:
                        type: string
                      last_update:
                        type: string
```

---

## 9. Summary

EPMPulse is designed with **simplicity first**:

1. **JSON state** - No database complexity for MVP
2. **Flask API** - Lightweight, team-familiar framework  
3. **Simple auth** - API keys, not OAuth complexity
4. **Full canvas replace** - Easier to reason about than partial updates
5. **Clear integration points** - Groovy and Python templates ready

**Scalability path** to Oracle AI DB is defined but not required for MVP. Migration triggers are documented.

**Risk mitigation** focuses on EPM connectivity (retries), state integrity (atomic writes), and monitoring (health checks).

**Team handoff** supported by comprehensive documentation, modular code structure, and clear integration templates.

---

## 10. API References

### 10.1 Oracle EPM Cloud REST API

**Job Monitoring:**
```
GET <epm-server>/epm/rest/v1/jobRuns/<job-id>
```
- Returns current state of data exchange operations
- Use job ID from POST response to monitor progress
- Supports Groovy/BeanShell integration within EPM

**Job Status Response:**
```json
{
  "status": 0,
  "details": "Metadata import was successful",
  "jobId": 224,
  "jobName": "Import Account Metadata",
  "descriptiveStatus": "Completed",
  "links": [{
    "rel": "self",
    "href": "https://<server>/epm/rest/v1/jobRuns/224"
  }]
}
```

**Important Note:** 
- Oracle EPM REST API requires **job ID** for direct queries
- **Job name alone cannot query** specific job status directly
- Job name is returned in response for correlation only
- To find job by name: query recent jobs and filter client-side

**Documentation:**
- [Oracle EPM REST API Overview](https://docs.oracle.com/en/cloud/saas/enterprise-data-management-cloud/edmra/edmcs_restapi_overview.html)
- [Planning REST APIs](https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/prest/planning_rest_apis.html)
- [JobRuns Resource](https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/prest/about_the_rest_api_for_cloud_plan_budget_guide.html)

**HTTP Methods:**
| Method | Purpose |
|--------|---------|
| GET | Retrieve job status, resources |
| POST | Initiate data exchange, create resources |
| PUT | Update resources |
| DELETE | Remove resources |

**Integration Articles:**
- [EPM REST API Integration](https://blogs.perficient.com/2024/01/11/power-of-oracle-epm-integration-calling-external-restapi-for-enhanced-performance/)
- [ODI + EDMCS REST API](https://www.ateam-oracle.com/integrating-oracle-enterprise-data-management-cloud-services-dimension-data-into-oracle-autonomous-data-warehouse-with-rest-api-and-odi-on-the-marketplace)

---

### 10.2 Slack Canvas API

**Canvas Update Functions:**

#### `canvas_update_content` (Workflows/Functions)
```javascript
{
  "action": "append" | "prepend" | "replace",
  "content": { /* expanded_rich_text object */ },
  "canvas_update_type": "standalone" | "channel_canvas",
  "canvas_id": "CAN1234ABC",  // for standalone
  "channel_id": "C01234ABC"   // for channel_canvas
}
```

#### `canvases.edit` (REST API)
```json
{
  "canvas_id": "F0166DCSTS7",
  "changes": [{
    "operation": "insert_after" | "insert_at_start" | "insert_at_end" | "replace" | "delete",
    "section_id": "temp:C:VXX8e648e6984e441c6aa8c61173",
    "document_content": {
      "type": "markdown",
      "markdown": "## Status\n🟢 Planning: OK"
    }
  }]
}
```

**Operations:**
| Operation | Description |
|-----------|-------------|
| `insert_after` | Insert after specific section |
| `insert_at_start` | Add to beginning of canvas |
| `insert_at_end` | Add to end of canvas |
| `replace` | Replace section or entire canvas |
| `delete` | Delete specific section |

**Documentation:**
- [canvas_update_content Function](https://api.slack.com/reference/functions/canvas_update_content)
- [canvases.edit Method](https://docs.slack.dev/reference/methods/canvases.edit/)
- [Canvas Surface Docs](https://docs.slack.dev/surfaces/canvases/)
- [Rich Text Format](https://docs.slack.dev/surfaces/canvas-advanced/rich-text/)

**Important Notes:**
- Channel canvas updates post notifications
- Only one operation per `canvases.edit` call
- Use `canvases.sections.lookup` to get section IDs
- Supports markdown: bold, lists, checklists, tables, mentions

---

*Architecture Review Complete*  
*Ready for MVP Implementation*