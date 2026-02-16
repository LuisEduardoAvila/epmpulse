# EPMPulse

EPM Job Status Dashboard - bridging Oracle EPM Cloud with Slack Canvas.

## Quick Start

### 1. Installation

```bash
cd projects/epm-dashboard

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Set required environment variables:

```bash
export EPMPULSE_API_KEY="your_secret_api_key_here"
export SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
export SLACK_CANVAS_ID="Fcanvas-placeholder-id"
export LOG_LEVEL="INFO"  # Optional, default: INFO
```

### 3. Start the Server

```bash
python3 -m flask --app src.app run --host 0.0.0.0 --port 18800
```

Or use gunicorn for production:

```bash
gunicorn -w 4 -b 0.0.0.0:18800 "src.app:create_app()"
```

### 4. Update Status

From EPM Groovy rules or any HTTP client:

```bash
curl -X POST http://localhost:18800/api/v1/status \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_secret_api_key_here" \
  -d '{
    "app": "Planning",
    "domain": "Actual",
    "status": "Loading",
    "job_id": "LOAD_20260216_001"
  }'
```

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/status` | Update single app/domain status |
| POST | `/api/v1/status/batch` | Batch update multiple apps |
| GET | `/api/v1/status` | Get all statuses |
| GET | `/api/v1/status/{app}` | Get specific app status |
| POST | `/api/v1/canvas/sync` | Force canvas sync |
| GET | `/api/v1/health` | Health check |

### Request Format

```json
{
  "app": "Planning|FCCS|ARCS",
  "domain": "Actual|Budget|Forecast|Consolidation|Reconciliation",
  "status": "Blank|Loading|OK|Warning",
  "job_id": "Optional_correlation_id",
  "message": "Optional_message",
  "timestamp": "2026-02-16T14:30:00Z"
}
```

### Success Response

```json
{
  "success": true,
  "data": {
    "app": "Planning",
    "domain": "Actual",
    "status": "Loading",
    "job_id": "LOAD_20260216_001",
    "updated": "2026-02-16T14:30:00Z",
    "canvas_updated": true
  }
}
```

## Configuration

### apps.json

Configure your EPM applications and Slack channels in `config/apps.json`:

```json
{
  "apps": {
    "Planning": {
      "display_name": "Planning",
      "domains": ["Actual", "Budget", "Forecast"],
      "channels": ["C0123456789"]
    }
  }
}
```

## EPM Integration

### Groovy Business Rule Template

```groovy
String API_URL = "http://hspi.local:18800/api/v1/status"
String API_KEY = "epmpulse_key_xxx..."

def updateEPMStatus(String app, String domain, String status, String jobId) {
    def payload = [
        app: app,
        domain: domain,
        status: status,
        job_id: jobId
    ]
    
    def connection = new URL(API_URL).openConnection()
    connection.setRequestMethod("POST")
    connection.setRequestProperty("Content-Type", "application/json")
    connection.setRequestProperty("Authorization", "Bearer ${API_KEY}")
    connection.setDoOutput(true)
    
    def outputStream = connection.getOutputStream()
    outputStream.write(new groovy.json.JsonBuilder(payload).toString().getBytes("UTF-8"))
    outputStream.close()
    
    return connection.getResponseCode() == 200
}
```

### Python Client (ODI)

```python
import requests
import os

PULSE_URL = "http://hspi.local:18800"
PULSE_KEY = os.environ.get("EPMPULSE_API_KEY")

def update_status(app, domain, status, job_id=None):
    payload = {
        "app": app,
        "domain": domain,
        "status": status,
        "job_id": job_id
    }
    
    headers = {
        "Authorization": f"Bearer {PULSE_KEY}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{PULSE_URL}/api/v1/status", json=payload, headers=headers)
    return response.json()
```

## Development

### Running Tests

```bash
pytest tests/ -v --cov=src --cov-report=html
```

### Code Style

- Python 3.11+
- Black formatting (88 char line length)
- 80% test coverage minimum

### Project Structure

```
projects/epm-dashboard/
├── src/
│   ├── app.py              # Flask app factory
│   ├── config.py           # Configuration
│   ├── state/
│   │   ├── models.py       # Data classes
│   │   └── manager.py      # State persistence
│   ├── api/
│   │   ├── routes.py       # API endpoints
│   │   ├── validators.py   # Pydantic validators
│   │   └── errors.py       # Error handlers
│   ├── slack/
│   │   ├── client.py       # Slack SDK wrapper
│   │   ├── canvas.py       # Canvas management
│   │   └── blocks.py       # Canvas block generators
│   └── utils/
│       ├── logging_config.py
│       └── decorators.py
├── tests/
│   ├── test_api.py
│   └── test_state.py
├── config/
│   └── apps.json
├── scripts/
│   └── generate_api_key.py
├── requirements.txt
└── README.md
```

## Troubleshooting

### Common Issues

**API key not working:**
- Verify `EPMPULSE_API_KEY` is set correctly
- Check for extra whitespace in the key

**Canvas not updating:**
- Verify `SLACK_BOT_TOKEN` has canvas permissions
- Check `SLACK_CANVAS_ID` is correct

**File locking errors:**
- Ensure the `data/` directory is writable
- Check for zombie lock files

## License

MIT
