"""EPM REST API client with OAuth authentication.

Supports multi-server EPM environments (Planning, FCCS, ARCS)
with unified OAuth token management.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from requests.auth import HTTPBasicAuth


logger = logging.getLogger("epmpulse.epm")


@dataclass
class EPMJobStatus:
    """EPM job status response."""
    
    job_id: str
    job_name: str
    status: int
    descriptive_status: str  # "Pending", "Processing", "Completed", "Error"
    details: Optional[str] = None
    links: List[Dict[str, str]] = None
    
    @classmethod
    def from_response(cls, data: dict) -> "EPMJobStatus":
        """Create from EPM API response."""
        return cls(
            job_id=str(data.get("jobId", "")),
            job_name=data.get("jobName", ""),
            status=data.get("status", -1),
            descriptive_status=data.get("descriptiveStatus", "Unknown"),
            details=data.get("details"),
            links=data.get("links", [])
        )
    
    @property
    def is_complete(self) -> bool:
        """Check if job completed successfully."""
        return self.descriptive_status == "Completed"
    
    @property
    def is_error(self) -> bool:
        """Check if job failed."""
        return self.descriptive_status == "Error"
    
    @property
    def is_running(self) -> bool:
        """Check if job is still running."""
        return self.descriptive_status in ["Pending", "Processing"]


class EPMOAuthClient:
    """EPM REST API client with OAuth authentication.
    
    Supports multiple EPM servers (Planning, FCCS, ARCS) with
    single OAuth token for the domain.
    """
    
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "urn:opc:epm",
        servers: Optional[Dict[str, dict]] = None
    ):
        """Initialize EPM OAuth client.
        
        Args:
            token_url: OAuth token endpoint URL
            client_id: OAuth client ID
            client_secret: OAuth client secret
            scope: OAuth scope (default: urn:opc:epm)
            servers: Dict of server configs {server_id: {name, base_url}}
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.servers = servers or {}
        
        # Token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        
        # Request session for connection pooling
        self._session = requests.Session()
        
        logger.info(f"EPM client initialized with {len(self.servers)} servers")
    
    @classmethod
    def from_config(cls, config_path: Optional[Path] = None) -> "EPMOAuthClient":
        """Create client from configuration.
        
        Args:
            config_path: Path to config file (default: config/apps.json)
            
        Returns:
            Configured EPMOAuthClient
        """
        import json
        import os
        
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "apps.json"
        
        with open(config_path) as f:
            config = json.load(f)
        
        epm_config = config.get("epm", {})
        auth_config = epm_config.get("auth", {})
        servers_config = epm_config.get("servers", {})
        
        # Resolve environment variables in config
        def resolve_env(value: str) -> str:
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                return os.environ.get(env_var, value)
            return value
        
        return cls(
            token_url=auth_config.get("token_url", ""),
            client_id=resolve_env(auth_config.get("client_id", "")),
            client_secret=resolve_env(auth_config.get("client_secret", "")),
            scope=auth_config.get("scope", "urn:opc:epm"),
            servers={
                k: {
                    "name": v.get("name", k),
                    "base_url": v.get("base_url", "")
                }
                for k, v in servers_config.items()
            }
        )
    
    def _get_token(self) -> str:
        """Get OAuth access token (cached until expiry).
        
        Returns:
            Access token string
            
        Raises:
            requests.HTTPError: If token request fails
        """
        # Return cached token if still valid (with 60s buffer)
        if self._access_token and time.time() < (self._token_expires_at - 60):
            logger.debug("Using cached OAuth token")
            return self._access_token
        
        logger.info("Requesting new OAuth token")
        
        response = self._session.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope
            },
            timeout=30
        )
        response.raise_for_status()
        
        token_data = response.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        
        logger.info(f"OAuth token obtained, expires in {expires_in}s")
        
        return self._access_token
    
    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """Make authenticated request to EPM API.
        
        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional requests arguments
            
        Returns:
            Response object
        """
        token = self._get_token()
        
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"
        
        return self._session.request(
            method=method,
            url=url,
            headers=headers,
            timeout=kwargs.pop("timeout", 30),
            **kwargs
        )
    
    def get_job_status(
        self,
        server_id: str,
        job_id: str
    ) -> EPMJobStatus:
        """Get job status from specific EPM server.
        
        Args:
            server_id: Server identifier (e.g., "planning", "fccs", "arcs")
            job_id: EPM job ID from jobRuns endpoint
            
        Returns:
            EPMJobStatus object
            
        Raises:
            ValueError: If server_id not configured
            requests.HTTPError: If request fails
        """
        if server_id not in self.servers:
            raise ValueError(f"Unknown server: {server_id}")
        
        server = self.servers[server_id]
        url = f"{server['base_url']}/epm/rest/v1/jobRuns/{job_id}"
        
        logger.debug(f"Querying job {job_id} on {server_id}")
        
        response = self._make_request("GET", url)
        response.raise_for_status()
        
        return EPMJobStatus.from_response(response.json())
    
    def get_job_result(
        self,
        server_id: str,
        job_id: str
    ) -> dict:
        """Get detailed job result from EPM server.
        
        Args:
            server_id: Server identifier
            job_id: EPM job ID
            
        Returns:
            Raw job result data
        """
        if server_id not in self.servers:
            raise ValueError(f"Unknown server: {server_id}")
        
        server = self.servers[server_id]
        url = f"{server['base_url']}/epm/rest/v1/jobRuns/{job_id}/result"
        
        logger.debug(f"Querying job result {job_id} on {server_id}")
        
        response = self._make_request("GET", url)
        response.raise_for_status()
        
        return response.json()
    
    def poll_multi_server_job(
        self,
        server_jobs: Dict[str, str],
        timeout_minutes: int = 60,
        poll_interval_seconds: int = 30
    ) -> Dict[str, EPMJobStatus]:
        """Poll job status across multiple servers.
        
        Used for cross-pod jobs that span multiple EPM servers.
        
        Args:
            server_jobs: Dict mapping server_id -> job_id
            timeout_minutes: Maximum polling time
            poll_interval_seconds: Seconds between polls
            
        Returns:
            Dict of final statuses per server
        """
        import concurrent.futures
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        results = {}
        
        logger.info(f"Starting multi-server poll for {len(server_jobs)} servers")
        
        while time.time() - start_time < timeout_seconds:
            all_complete = True
            
            # Check each server's job
            for server_id, job_id in server_jobs.items():
                if server_id in results:
                    continue  # Already completed
                
                try:
                    status = self.get_job_status(server_id, job_id)
                    results[server_id] = status
                    
                    if not status.is_complete and not status.is_error:
                        all_complete = False
                        
                except Exception as e:
                    logger.warning(f"Failed to query {server_id}: {e}")
                    all_complete = False
            
            if all_complete:
                logger.info("All server jobs completed")
                return results
            
            logger.debug(f"Waiting {poll_interval_seconds}s before next poll")
            time.sleep(poll_interval_seconds)
        
        logger.warning(f"Multi-server poll timed out after {timeout_minutes} minutes")
        return results
    
    def get_server_url(self, server_id: str) -> str:
        """Get base URL for server.
        
        Args:
            server_id: Server identifier
            
        Returns:
            Base URL string
        """
        if server_id not in self.servers:
            raise ValueError(f"Unknown server: {server_id}")
        return self.servers[server_id]["base_url"]
    
    def get_app_server(self, app_name: str, config_path: Optional[Path] = None) -> str:
        """Get server ID for application.
        
        Args:
            app_name: Application name (Planning, FCCS, ARCS)
            config_path: Path to config file
            
        Returns:
            Server ID (e.g., "planning", "fccs", "arcs")
        """
        import json
        
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "apps.json"
        
        with open(config_path) as f:
            config = json.load(f)
        
        app_config = config.get("apps", {}).get(app_name, {})
        return app_config.get("server", app_name.lower())
    
    def invalidate_token(self):
        """Force token refresh on next request."""
        self._access_token = None
        self._token_expires_at = 0
        logger.info("OAuth token invalidated")
