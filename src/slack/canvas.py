"""Canvas update manager with debouncing for EPMPulse."""

import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime

from .client import SlackClient
from .blocks import build_app_block, build_canvas_state


class CanvasManager:
    """Manages Slack Canvas updates with debouncing."""
    
    DEBOUNCE_INTERVAL = 2.0  # seconds
    DEFAULT_CANVAS_ID = 'Fcanvas_placeholder'
    
    def __init__(self, slack_client: Optional[SlackClient] = None):
        """Initialize Canvas manager.
        
        Args:
            slack_client: SlackClient instance (creates new if None)
        """
        self.slack_client = slack_client or SlackClient()
        self._last_update_time = 0.0
        self._pending_update = False
        self._update_lock = threading.Lock()
        self._canvas_id = self._get_canvas_id()
    
    def _get_canvas_id(self) -> str:
        """Get canvas ID from config or use placeholder."""
        import os
        canvas_id = os.environ.get('SLACK_CANVAS_ID', self.DEFAULT_CANVAS_ID)
        return canvas_id if canvas_id != self.DEFAULT_CANVAS_ID else self.DEFAULT_CANVAS_ID
    
    def _should_update_now(self) -> bool:
        """Check if update should execute now (debouncing check).
        
        Returns:
            True if should update now, False if should defer
        """
        current_time = time.time()
        return (current_time - self._last_update_time) >= self.DEBOUNCE_INTERVAL
    
    def _update_canvas(self, blocks: list) -> bool:
        """Actually perform the canvas update.
        
        Args:
            blocks: Canvas blocks to set
            
        Returns:
            True if successful, False otherwise
        """
        if not self.slack_client.is_configured():
            print("Slack client not configured, skipping canvas update")
            return False
        
        try:
            # For MVP, we'll use the canvas_id from environment
            canvas_id = self._canvas_id
            
            # Update the canvas document
            result = self.slack_client.client.canvases_edit(
                canvas_id=canvas_id,
                document_json={'blocks': blocks}
            )
            
            self._last_update_time = time.time()
            return True
            
        except Exception as e:
            print(f"Canvas update failed: {e}")
            return False
    
    def update_canvas_for_domain(
        self,
        app_name: str,
        domain_name: str,
        status: str
    ) -> bool:
        """Update canvas for a specific domain.
        
        Args:
            app_name: Application name
            domain_name: Domain name
            status: New status value
            
        Returns:
            True if update was triggered, False otherwise
        """
        with self._update_lock:
            if self._should_update_now():
                # Fetch state
                from ..state.manager import StateManager
                state_mgr = StateManager()
                state = state_mgr.read()
                
                # Build blocks for this app
                if app_name in state.apps:
                    domain = state.apps[app_name].domains.get(domain_name)
                    if domain:
                        blocks = build_app_block(
                            app_name=app_name,
                            display_name=state.apps[app_name].display_name,
                            domains={domain_name: domain.to_dict()}
                        )
                    else:
                        blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_{domain_name}_'}},
                                  {'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'{self._get_status_icon(status)} {status}'}]}]
                else:
                    blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{app_name}*'}},
                              {'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'_{domain_name}_'}, {'type': 'mrkdwn', 'text': f'{self._get_status_icon(status)} {status}'}]}]
                
                return self._update_canvas(blocks)
            else:
                self._pending_update = True
                return False
    
    def sync_canvas(self) -> str:
        """Force canvas synchronization.
        
        Returns:
            Canvas ID that was synced
        """
        from ..state.manager import StateManager
        state_mgr = StateManager()
        state = state_mgr.read()
        
        blocks = build_canvas_state(state.to_dict())
        self._update_canvas(blocks)
        
        return self._canvas_id
    
    def _get_status_icon(self, status: str) -> str:
        """Get status icon.
        
        Args:
            status: Status value
            
        Returns:
            Icon string
        """
        icons = {
            'Blank': '⚪',
            'Loading': '🟡',
            'OK': '🟢',
            'Warning': '🔴'
        }
        return icons.get(status, '⚪')
    
    def _process_pending_update(self) -> bool:
        """Process any pending canvas update.
        
        Returns:
            True if update was performed, False otherwise
        """
        if not self._pending_update:
            return False
        
        if self._should_update_now():
            from ..state.manager import StateManager
            state_mgr = StateManager()
            state = state_mgr.read()
            
            blocks = build_canvas_state(state.to_dict())
            result = self._update_canvas(blocks)
            self._pending_update = False
            return result
        
        return False
    
    def update_canvas_for_app(self, app_name: str) -> bool:
        """Update canvas for an entire app.
        
        Args:
            app_name: Application name
            
        Returns:
            True if update was triggered, False otherwise
        """
        with self._update_lock:
            from ..state.manager import StateManager
            state_mgr = StateManager()
            state = state_mgr.read()
            
            if app_name not in state.apps:
                return False
            
            app = state.apps[app_name]
            domains = {
                name: domain.to_dict()
                for name, domain in app.domains.items()
            }
            
            blocks = build_app_block(app_name, app.display_name, domains)
            
            if self._should_update_now():
                return self._update_canvas(blocks)
            else:
                self._pending_update = True
                return False
