"""Data models for EPMPulse state management."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class Domain:
    """Represents a domain within an application."""
    status: str
    job_id: Optional[str] = None
    message: Optional[str] = None
    updated: Optional[str] = None
    duration_sec: Optional[int] = None
    
    VALID_STATUSES = {"Blank", "Loading", "OK", "Warning"}
    
    def __post_init__(self):
        if self.status not in self.VALID_STATUSES:
            raise ValueError(
                f"Status must be one of: {', '.join(self.VALID_STATUSES)}"
            )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Domain":
        """Create Domain from dictionary."""
        return cls(
            status=data.get("status", "Blank"),
            job_id=data.get("job_id"),
            message=data.get("message"),
            updated=data.get("updated"),
            duration_sec=data.get("duration_sec")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Domain to dictionary."""
        return {
            "status": self.status,
            "job_id": self.job_id,
            "message": self.message,
            "updated": self.updated,
            "duration_sec": self.duration_sec
        }


@dataclass
class App:
    """Represents an EPM application with its domains."""
    name: str
    display_name: str
    domains: Dict[str, Domain] = field(default_factory=dict)
    channels: list = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "App":
        """Create App from dictionary."""
        domains = {
            domain_name: Domain.from_dict(domain_data)
            for domain_name, domain_data in data.get("domains", {}).items()
        }
        return cls(
            name=name,
            display_name=data.get("display_name", name),
            domains=domains,
            channels=data.get("channels", [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert App to dictionary."""
        return {
            "display_name": self.display_name,
            "channels": self.channels,
            "domains": {
                name: domain.to_dict()
                for name, domain in self.domains.items()
            }
        }


@dataclass
class State:
    """Main state container for EPMPulse."""
    version: str = "1.0"
    last_updated: Optional[str] = None
    apps: Dict[str, App] = field(default_factory=dict)
    recent_jobs: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.metadata:
            from datetime import datetime, timezone
            self.metadata = {
                "created": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "schema_version": "1.0"
            }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "State":
        """Create State from dictionary."""
        apps = {
            app_name: App.from_dict(app_name, app_data)
            for app_name, app_data in data.get("apps", {}).items()
        }
        return cls(
            version=data.get("version", "1.0"),
            last_updated=data.get("last_updated"),
            apps=apps,
            recent_jobs=data.get("recent_jobs", []),
            metadata=data.get("metadata", {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert State to dictionary."""
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "metadata": self.metadata,
            "apps": {
                name: app.to_dict()
                for name, app in self.apps.items()
            },
            "recent_jobs": self.recent_jobs
        }
    
    def add_domain(self, app_name: str, domain_name: str, domain: Domain):
        """Add or update a domain in the state."""
        if app_name not in self.apps:
            self.apps[app_name] = App(name=app_name, display_name=app_name)
        self.apps[app_name].domains[domain_name] = domain
