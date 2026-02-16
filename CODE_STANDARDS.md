# EPMPulse Code Standards

**Version:** 1.0  
**Date:** 2026-02-16  
**Project:** EPMPulse - EPM Job Status Dashboard

---

## 1. Language & Framework

- **Language:** Python 3.11+
- **Framework:** Flask 3.0+
- **API Style:** RESTful JSON
- **Async:** Use threading for concurrent operations, not asyncio

---

## 2. Project Structure

```
epmpulse/
├── src/
│   ├── __init__.py
│   ├── app.py                 # Flask application factory
│   ├── config.py              # Configuration management
│   ├── state/
│   │   ├── __init__.py
│   │   ├── manager.py         # JSON state file operations
│   │   └── models.py          # Data classes (Status, App, etc.)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py          # Flask route definitions
│   │   ├── validators.py      # Request validation
│   │   └── errors.py          # Error handlers
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── client.py          # Slack SDK wrapper
│   │   ├── canvas.py          # Canvas update logic
│   │   └── blocks.py          # Canvas block generators
│   ├── epm/
│   │   ├── __init__.py
│   │   └── pull_client.py     # EPM REST API polling
│   └── utils/
│       ├── __init__.py
│       ├── logging_config.py  # Structured logging
│       └── decorators.py      # Retry, auth decorators
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_state.py
│   └── test_slack.py
├── config/
│   ├── apps.json              # App/domain configuration
│   └── settings.yaml          # Runtime settings
├── data/
│   ├── apps_status.json       # State file (gitignored)
│   └── backups/               # Hourly backups
├── docs/
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 3. Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| **Modules** | Lowercase with underscores | `state_manager.py` |
| **Classes** | PascalCase | `StatusManager`, `SlackClient` |
| **Functions** | Lowercase with underscores | `update_status()`, `get_app_status()` |
| **Constants** | UPPERCASE_WITH_UNDERSCORES | `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT` |
| **Variables** | Lowercase with underscores | `app_name`, `job_id` |
| **Private** | Leading underscore | `_validate_payload()`, `_internal_state` |
| **Type Hints** | Use everywhere | `def update(app: str) -> dict:` |

---

## 4. Code Style

### 4.1 General Rules

- **Line length:** 88 characters (Black default)
- **Indentation:** 4 spaces
- **Quotes:** Double for strings, single for dict keys
- **Docstrings:** Google style
- **Comments:** Explain WHY, not WHAT

### 4.2 Function Standards

```python
def update_app_status(
    app: str,
    domain: str,
    status: str,
    job_id: Optional[str] = None,
    message: Optional[str] = None
) -> dict:
    """Update status for a specific app/domain.
    
    Args:
        app: Application name (Planning, FCCS, ARCS)
        domain: Domain within app (e.g., Actual, Budget)
        status: New status (Blank, Loading, OK, Warning)
        job_id: Optional job correlation ID
        message: Optional status message
        
    Returns:
        dict: Update result with timestamp
        
    Raises:
        ValueError: If app or status is invalid
        StateError: If state file cannot be written
    """
    # Implementation
    pass
```

### 4.3 Error Handling

```python
# Specific exceptions, not broad except
try:
    result = process_request(data)
except ValueError as e:
    logger.warning(f"Invalid request: {e}")
    return {"error": str(e)}, 400
except StateError as e:
    logger.error(f"State file error: {e}")
    return {"error": "Internal state error"}, 500
except requests.Timeout:
    logger.warning("Slack API timeout")
    return {"error": "Slack timeout"}, 503
```

---

## 5. State Management Standards

### 5.1 File Locking (Required)

```python
import fcntl
import json
from pathlib import Path

def atomic_write_state(state: dict, filepath: Path) -> None:
    """Write state atomically with file locking."""
    temp_path = filepath.with_suffix('.tmp')
    
    with open(temp_path, 'w') as f:
        # Acquire exclusive lock
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    # Atomic rename
    temp_path.rename(filepath)
```

### 5.2 State Structure

```json
{
  "version": "1.0",
  "last_updated": "2026-02-16T14:32:00Z",
  "apps": {
    "Planning": {
      "domains": {
        "Actual": {
          "status": "OK",
          "job_id": "LOAD_20260216_001",
          "updated": "2026-02-16T14:30:00Z",
          "message": null
        }
      }
    }
  },
  "job_id_map": {
    "LOAD_20260216_001": {
      "apps": ["Planning"],
      "domains": ["Actual"],
      "status": "completed"
    }
  }
}
```

---

## 6. API Standards

### 6.1 Request/Response Format

**Success Response (200):**
```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-02-16T14:32:00Z"
}
```

**Error Response (4xx/5xx):**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_STATUS",
    "message": "Status must be one of: Blank, Loading, OK, Warning"
  },
  "timestamp": "2026-02-16T14:32:00Z"
}
```

### 6.2 HTTP Status Codes

| Code | Use Case |
|------|----------|
| 200 | Success |
| 400 | Bad request (validation error) |
| 401 | Unauthorized (invalid API key) |
| 404 | App or domain not found |
| 422 | Unprocessable (status transition invalid) |
| 429 | Rate limited |
| 500 | Internal server error |
| 503 | Service unavailable (Slack down) |

---

## 7. Slack Integration Standards

### 7.1 Canvas Updates

- Use **section-based updates** (not full replace)
- Implement **debouncing** (2-second minimum between updates)
- Pre-define section IDs: `{app}_{domain}_section`
- Handle rate limits with exponential backoff

### 7.2 Error Recovery

```python
MAX_SLACK_RETRIES = 3
SLACK_BACKOFF_SECONDS = [1, 2, 4]  # Exponential

def update_canvas_with_retry(canvas_id: str, section_id: str, content: str) -> bool:
    for attempt, backoff in enumerate(SLACK_BACKOFF_SECONDS):
        try:
            return slack.canvases.edit(canvas_id, section_id, content)
        except SlackRateLimitError as e:
            if attempt < MAX_SLACK_RETRIES - 1:
                time.sleep(backoff)
            else:
                logger.error(f"Slack rate limit exceeded: {e}")
                return False
```

---

## 8. EPM Pull Mode Standards

### 8.1 Polling Configuration

```python
POLL_CONFIG = {
    "enabled": True,
    "interval_seconds": 30,
    "max_duration_minutes": 60,
    "max_retries": 3
}
```

### 8.2 Job ID Storage

- Store job_id when receiving "Loading" status
- Map job_id → apps/domains for quick lookup
- Clean up completed job_ids after 24 hours

---

## 9. Testing Standards

### 9.1 Test Structure

```python
# tests/test_state.py
import pytest
from src.state.manager import StateManager

class TestStateManager:
    """Test state file operations."""
    
    def test_atomic_write_creates_backup(self, tmp_path):
        """Atomic write should create temp file then rename."""
        manager = StateManager(tmp_path / "test.json")
        # Test implementation
        
    def test_concurrent_access_handled(self, tmp_path):
        """File locking should prevent corruption."""
        # Test implementation
```

### 9.2 Coverage Requirements

- **Minimum:** 80% code coverage
- **Critical paths:** 100% (state management, API routes)
- Use `pytest-cov` for coverage reports

---

## 10. Documentation Standards

### 10.1 README Sections

```markdown
# EPMPulse

## Quick Start
## Installation
## Configuration
## API Reference
## Troubleshooting
## Development
```

### 10.2 Code Comments

```python
# GOOD: Explain why
# Debounce to avoid Slack rate limits (50/min)
if time_since_last_update < 2:
    return

# BAD: Restates the code
# Check if time is less than 2
if time_since_last_update < 2:
    return
```

---

## 11. Security Standards

### 11.1 Secrets Management

```python
# Use environment variables, not hardcoded
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
EPM_PASSWORD = os.environ["EPM_PASSWORD"]
API_KEY = os.environ["EPMPULSE_API_KEY"]
```

### 11.2 API Key Validation

```python
from functools import wraps
from flask import request, abort

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key or key != os.environ["EPMPULSE_API_KEY"]:
            abort(401, "Invalid or missing API key")
        return f(*args, **kwargs)
    return decorated
```

---

## 12. Logging Standards

### 12.1 Log Levels

| Level | Use Case | Example |
|-------|----------|---------|
| DEBUG | Detailed diagnostics | Request payload inspection |
| INFO | Normal operations | Status update received |
| WARNING | Recoverable issues | Slack timeout, retrying |
| ERROR | Failed operations | State file write failed |
| CRITICAL | System failure | Cannot initialize state |

### 12.2 Structured Logging

```python
import logging
import json

logger = logging.getLogger("epmpulse")

def log_status_update(app: str, domain: str, status: str, job_id: str):
    logger.info(json.dumps({
        "event": "status_update",
        "app": app,
        "domain": domain,
        "status": status,
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat()
    }))
```

---

## 13. Deployment Standards

### 13.1 Environment Variables

```bash
# Required
EPMPULSE_API_KEY=secure_random_key
SLACK_BOT_TOKEN=xoxb-...

# Optional
EPM_SERVER=planning.oraclecloud.com
POLL_ENABLED=true
LOG_LEVEL=INFO
```

### 13.2 Health Check Endpoint

```python
@app.route("/api/v1/health")
def health_check():
    return {
        "status": "healthy",
        "checks": {
            "state_file": check_state_file(),
            "slack_api": check_slack_connection()
        }
    }
```

---

*Code Standards Complete*  
*Ready for Implementation*
