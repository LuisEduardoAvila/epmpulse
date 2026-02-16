"""State manager for EPMPulse with file locking and atomic writes.

Handles all JSON file operations for persistent state management.
Uses fcntl for exclusive file locking to handle concurrent updates.
Implements atomic writes (write to temp, then rename) to prevent corruption.
"""

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from src.state.models import State, App, Domain


class StateError(Exception):
    """Exception raised for state file operations failures."""
    pass


class StateManager:
    """Manages EPMPulse state with file locking and atomic writes."""

    def __init__(self, state_file: Optional[Path] = None):
        """Initialize state manager.
        
        Args:
            state_file: Path to state JSON file. Defaults to data/apps_status.json
        """
        self.state_file = state_file or Path(__file__).parent.parent.parent / "data" / "apps_status.json"
        self._lock_fd = None
    
    def _ensure_dir(self):
        """Ensure data directory exists."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def read(self) -> State:
        """Read state from JSON file."""
        self._ensure_dir()
        
        if not self.state_file.exists():
            return State()
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            return State.from_dict(data)
        except json.JSONDecodeError as e:
            raise StateError(f"Invalid JSON in state file: {e}")
        except IOError as e:
            raise StateError(f"Failed to read state file: {e}")
    
    def write(self, state: State) -> None:
        """Write state atomically using temp file + rename."""
        self._ensure_dir()
        
        # Update timestamp
        state.last_updated = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Atomic write pattern
        fd, tmp_path = tempfile.mkstemp(
            dir=self.state_file.parent,
            suffix='.tmp'
        )
        
        try:
            with os.fdopen(fd, 'w') as f:
                # Acquire exclusive lock on temp file
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(state.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            os.replace(tmp_path, str(self.state_file))
        except Exception as e:
            # Cleanup on error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise StateError(f"Failed to write state file: {e}")
    
    def update(
        self,
        app_name: str,
        domain_name: str,
        status: str,
        job_id: Optional[str] = None,
        message: Optional[str] = None,
        duration_sec: Optional[int] = None
    ) -> Domain:
        """Update a domain's status.
        
        Args:
            app_name: Application name
            domain_name: Domain name
            status: New status value
            job_id: Optional job ID
            message: Optional message
            duration_sec: Optional duration
            
        Returns:
            Updated Domain object
        """
        state = self.read()
        
        # Create or update domain
        domain = Domain(
            status=status,
            job_id=job_id,
            message=message,
            updated=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            duration_sec=duration_sec
        )
        
        state.add_domain(app_name, domain_name, domain)
        self.write(state)
        
        return domain
    
    def batch_update(self, updates: list) -> Dict[str, Any]:
        """Update multiple domains.
        
        Args:
            updates: List of update dicts
            
        Returns:
            Dict with update results
        """
        state = self.read()
        
        results = []
        for update in updates:
            app_name = update.get('app')
            domain_name = update.get('domain')
            status = update.get('status')
            job_id = update.get('job_id')
            message = update.get('message')
            
            domain = Domain(
                status=status,
                job_id=job_id,
                message=message,
                updated=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                duration_sec=None
            )
            state.add_domain(app_name, domain_name, domain)
            results.append({
                'app': app_name,
                'domain': domain_name,
                'status': status
            })
        
        self.write(state)
        
        return {
            'updated_count': len(results),
            'updates': results
        }
    
    def get_all(self) -> Dict[str, Any]:
        """Get all statuses formatted for API response."""
        state = self.read()
        
        apps_data = {}
        for app_name, app in state.apps.items():
            apps_data[app_name] = {}
            for domain_name, domain in app.domains.items():
                apps_data[app_name][domain_name] = {
                    'status': domain.status,
                    'job_id': domain.job_id,
                    'message': domain.message,
                    'updated': domain.updated,
                    'duration_sec': domain.duration_sec
                }
        
        return {
            'last_updated': state.last_updated,
            'apps': apps_data
        }
    
    def get_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Get status for specific app.
        
        Args:
            app_name: Application name
            
        Returns:
            Dict with app data or None
        """
        state = self.read()
        
        if app_name not in state.apps:
            return None
        
        app = state.apps[app_name]
        domains = {}
        for domain_name, domain in app.domains.items():
            domains[domain_name] = {
                'status': domain.status,
                'job_id': domain.job_id,
                'updated': domain.updated
            }
        
        return {
            'app': app_name,
            'domains': domains,
            'last_updated': state.last_updated
        }
    
    def __enter__(self) -> "StateManager":
        """Context manager entry - acquire lock."""
        self._ensure_dir()
        lock_path = self.state_file.with_suffix('.lock')
        self._lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lock."""
        if self._lock_fd:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
        return False
