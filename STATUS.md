# EPM Dashboard Project Status

**Status:** ✅ Architecture Complete → Ready for MVP Implementation  
**Date:** 2026-02-16  
**Architecture Review:** Complete (see ARCHITECTURE.md)  

---

## Project Definition

**Name:** EPMPulse (working title)  
**Purpose:** Real-time EPM job status dashboard for Slack Canvas  
**Domain:** Oracle EPM Cloud (Planning, FCCS, ARCS)  
**Display:** Slack Canvas (persistent, channel-based)  

---

## Requirements Summary

### Applications (Initial: 5-6, Expansible)

| App | Channel | Domains/Notes |
|-----|---------|---------------|
| **Planning** | Main channel | Actual, Budget, Forecast |
| **FCCS** | Main channel | Consolidation |
| **ARCS** | ARCS support channel | Account Reconciliation |
| *[expandable]* | *[new channels]* | *As needed* |

### Status Lifecycle

```
[Blank] → [Loading] → [OK] 
              ↓
         [Warning] (on error)
```

- **Blank**: Initial state  
- **Loading**: Job started  
- **OK**: Job completed successfully  
- **Warning**: Job failed or had errors  

Status persists until next job changes it.

### Multi-App Impact

| Pipeline Type | Affected Apps |
|--------------|---------------|
| Planning-only | Planning |
| FCCS-only | FCCS |
| Full Load | Planning + FCCS |
| *Custom* | *Configurable* |

---

## Integration Architecture

### Trigger Options (Chosen: Flexible)

**Option A: Groovy Business Rule (EPM-native)**
```groovy
// Called as step in EPM data exchange
import com.slack.api.*

// Update status at job start
SlackStatus.update(app: "Planning", domain: "Actual", status: "Loading")

// Update on completion
SlackStatus.update(app: "Planning", domain: "Actual", status: "OK")
```

**Option B: Python Script (ODI Integration)**
```python
# Called from ODI via EPM Agent
from epm_pulse import update_status

update_status(
    apps=["Planning", "FCCS"],
    domains=["Actual"],
    status="Loading",
    job_id=extract_id
)
```

**Recommended:** Hybrid approach — Groovy for EPM-native, Python for ODI pipelines.

### Slack Canvas Structure

**Main Channel Dashboard:**
```
┌─────────────────────────────────────┐
│  EPM Dashboard - Main Apps          │
├─────────────────────────────────────┤
│                                     │
│  🟢 Planning      [Actual]         │
│                   [Budget]         │
│                   [Forecast]       │
│                                     │
│  🟢 FCCS          [Consolidation]  │
│                                     │
│  Last updated: 14:32 UTC           │
│  Job ID: LOAD_20250216_001           │
└─────────────────────────────────────┘
```

**ARCS Support Channel:**
```
┌─────────────────────────────────────┐
│  ARCS Dashboard                     │
├─────────────────────────────────────┤
│                                     │
│  🟡 ARCS          [Reconciliation] │
│                   Loading...       │
│                                     │
│  Last updated: 14:30 UTC           │
└─────────────────────────────────────┘
```

---

## Technical Architecture

> ⚠️ **Environment Separation**: EPMPulse runs in your isolated environment (not OpenClaw host).

### Components

```
┌─────────────────────────────────┐
│       Oracle EPM Cloud          │
│  ┌──────────┐  ┌──────────┐     │
│  │ Planning │  │  FCCS    │     │
│  └────┬─────┘  └────┬─────┘     │
│       │             │           │
│  ┌────▼─────┐  ┌───▼────────┐  │
│  │ Groovy   │  │ ODI Python │  │
│  │ Rules    │  │ Scripts    │  │
│  └────┬─────┘  └────┬───────┘  │
└───────┼────────────┼───────────┘
        │            │
        └──────┬─────┘
               │ HTTP API
               ▼
┌─────────────────────────────┐    ┌──────────────┐
│  EPMPulse (Your Env)        │    │  Slack API   │
│  ┌──────────────────────┐   │    │  (Tokens in  │
│  │ Flask API Server     │   │◄───┤  your env)   │
│  │ Port: 18800 (example)│   │    └──────────────┘
│  ├──────────────────────┤   │
│  │ JSON State File      │   │
│  │ apps_status.json     │   │
│  └──────────────────────┘   │
└─────────────────────────────┘
         │
         │ Canvas Updates
         ▼
┌──────────────────────────────┐
│  Slack Canvas                │
│  ├─ Main Channel             │
│  │   Planning | FCCS        │
│  └─ ARCS Support Channel     │
└──────────────────────────────┘
```

### Data Model (JSON State File)

**File:** `apps_status.json`

```json
{
  "last_updated": "2026-02-16T14:32:00Z",
  "apps": {
    "Planning": {
      "Actual": {
        "status": "OK",
        "job_id": "LOAD_20260216_001",
        "updated": "2026-02-16T14:30:00Z"
      },
      "Budget": {
        "status": "Loading",
        "job_id": "LOAD_20260216_002",
        "updated": "2026-02-16T14:32:00Z"
      },
      "Forecast": {
        "status": "OK",
        "job_id": "LOAD_20260216_001",
        "updated": "2026-02-16T14:30:00Z"
      }
    },
    "FCCS": {
      "Consolidation": {
        "status": "OK",
        "job_id": "FULL_20260216_001",
        "updated": "2026-02-16T14:30:00Z"
      }
    },
    "ARCS": {
      "Reconciliation": {
        "status": "Warning",
        "job_id": "ARCS_20260216_001",
        "error": "Timeout on batch 3",
        "updated": "2026-02-16T14:25:00Z"
      }
    }
  }
}
```

**History:** None (Oracle DB maintains audit trail)

---

## MVP Definition

### Phase 1: Single App Proof of Concept

**Scope:**
- [ ] One EPM application (Planning)
- [ ] One domain (Actual)
- [ ] Manual API trigger
- [ ] Single Slack canvas
- [ ] Status: Loading → OK/Warning

**Tech Stack:**
- Python/Flask API (local to OpenClaw host)
- Slack Bolt SDK
- Simple JSON state file

### Phase 2: Multi-App & Automation

- [ ] Add FCCS
- [ ] Groovy integration (EPM business rule)
- [ ] Domain support (Budget, Forecast)
- [ ] Multi-app pipeline support
- [ ] History/audit trail

### Phase 3: Production Features

- [ ] Multiple channels (ARCS support)
- [ ] ODI Python integration
- [ ] Webhook-based (instead of polling)
- [ ] Dashboard customization
- [ ] Alerts/notifications

---

## Integration Points

### From EPM (Groovy)

```groovy
// Called as data exchange step
def updateDashboard(String app, String domain, String status, String jobId) {
    def url = "http://hspi.local:18800/api/status"
    def payload = [
        app: app,
        domain: domain,
        status: status,
        job_id: jobId,
        timestamp: new Date().toString()
    ]
    // POST to EPMPulse API
}
```

### From ODI (Python)

```python
# Called via EPM Agent command
import requests

def notify_job_start(apps, domain):
    for app in apps:
        requests.post("http://hspi.local:18800/api/status", json={
            "app": app,
            "domain": domain,
            "status": "Loading",
            "job_id": odi_context.job_id
        })

def notify_job_complete(apps, domain, success):
    status = "OK" if success else "Warning"
    # POST updates
```

---

## Constraints (Clarified)

| Aspect | Constraint | Implication |
|--------|------------|-------------|
| **Environment** | Separated from OpenClaw | You build/deploy, I provide design |
| **Slack tokens** | In separated environment | Not accessible by OpenClaw agent |
| **State** | JSON file (persistent) | Simple, single source for Slack |
| **History** | Not in EPMPulse | Maintained in Oracle DB |

## Design Decisions

1. **API Server Location:** ⚠️ Separated environment (you manage)
2. **Authentication:** ⚠️ Managed in your environment (tokens not here)
3. **State Persistence:** ✅ JSON file (lightweight)
4. **History:** ✅ None (Oracle DB handles audit trail)
5. **Multi-domain:** Planning shows all 3 domains (Actual, Budget, Forecast)
6. **Job correlation:** Job ID links EPM → EPMPulse → display
7. **Timezones:** UTC for API, Europe/London for display

## My Role

- ✅ Architecture design
- ✅ Code templates/review
- ✅ Implementation guidance
- ❌ Direct access to env
- ❌ Token management
- ❌ Deployment

---

## Next Steps

**Immediate:**
1. Create Slack app/bot token
2. Design Canvas layout (JSON structure)
3. Build Flask API skeleton
4. Test Slack Canvas update API

**After MVP:**
5. Groovy rule in EPM dev environment
6. Integration testing
7. Deploy to production EPM

---

## Resources

| Resource | Location | Status |
|----------|----------|--------|
| Project docs | `projects/epm-dashboard/` | 🔄 Created |
| Slack API | api.slack.com | Pending setup |
| EPM Groovy docs | Oracle docs | Reference |
| **Oracle Autonomous AI DB** | Serverless | ✅ Available |

### Oracle Autonomous AI Database (Serverless)

**Use Cases:**
- Alternative to JSON file for state persistence
- Real-time status queries
- Cross-job analytics (if needed beyond EPM history)
- Multi-instance dashboard sync

**Trade-offs:**

| Option | Pros | Cons |
|--------|------|------|
| **JSON file** | Simple, no DB overhead, fast reads | Single instance only |
| **Oracle AI DB** | Scalable, queryable, multi-instance | Adds latency, more complex |

**Recommendation:** Start with JSON. Migrate to Oracle AI DB if:
- Need multiple EPMPulse instances
- Want SQL queries for status analytics
- Need distributed state across regions

---

---

## Architecture Review Summary (2026-02-16)

**Document:** `ARCHITECTURE.md` (comprehensive, 47KB)

### Key Decisions
1. **API**: 6 REST endpoints (status CRUD, canvas sync, health)
2. **Auth**: Simple API keys (no OAuth complexity)
3. **State**: JSON file with file locking for concurrency
4. **Canvas**: Full replace strategy (simpler than partial)
5. **Integration**: Groovy template + Python client module
6. **Scale**: Oracle AI DB migration path defined with triggers

### Risk Mitigations
- EPM connectivity: Retry logic in Groovy/Python
- File corruption: Atomic writes + validation
- Slack limits: Debouncing (2s min interval)
- Idle detection: Alert if no updates in 24h

### MVP Timeline
- Week 1-2: Core Flask API + state management
- Week 3: Slack Canvas integration
- Week 4: End-to-end integration
- Week 5: Polish + team handoff

### Next Session Tasks
1. Create Slack app/bot token
2. Build Flask project structure
3. Implement state_manager.py
4. Build canvas block generator
5. Test manual canvas update

**Resumed:** When ready to build MVP  
**Priority:** Medium (architecture complete)
