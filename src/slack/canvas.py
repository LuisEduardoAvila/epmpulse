"""Canvas update manager with debouncing for EPMPulse."""

import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

from .client import SlackClient
from .blocks import build_app_block, build_canvas_state


class CanvasManager:
    """Manages Slack Canvas updates with debouncing."""
    
    DEBOUNCE_INTERVAL = 2.0  # seconds
    DEFAULT_CANVAS_ID = 'Fcanvas_placeholder'
    PROCESSOR_INTERVAL = 0.5  # Check for pending updates every 0.5 seconds
    
    def __init__(self, slack_client: Optional[SlackClient] = None):
        """Initialize Canvas manager.
        
        Args:
            slack_client: SlackClient instance (creates new if None)
        """
        self.slack_client = slack_client or SlackClient()
        self._last_update_time = 0.0
        self._pending_update = None  # Store blocks instead of just boolean
        self._update_lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._processor_thread: Optional[threading.Thread] = None
        self._stop_processor = threading.Event()
        self._canvas_id = self._get_canvas_id()
        
        # Start the background processor thread
        self._start_processor()
    
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
    
    def _process_pending(self):
        """Process pending updates in a background thread."""
        while not self._stop_processor.is_set():
            with self._update_lock:
                if self._pending_update is not None:
                    # Check if we should update now
                    if self._should_update_now():
                        blocks = self._pending_update
                        self._pending_update = None
                        self._update_canvas(blocks)
                    else:
                        # Schedule another check
                        delay = self.PROCESSOR_INTERVAL
                        self._timer = threading.Timer(delay, self._process_pending)
                        self._timer.daemon = True
                        self._timer.start()
                        break
                else:
                    # No pending update, wait a bit before checking again
                    pass
            
            # Small sleep to prevent tight loop
            time.sleep(self.PROCESSOR_INTERVAL)
    
    def _start_processor(self):
        """Start the background processor thread."""
        self._stop_processor.clear()
        self._processor_thread = threading.Thread(target=self._process_pending_loop, daemon=True)
        self._processor_thread.start()
    
    def _process_pending_loop(self):
        """Main loop for processing pending updates."""
        while not self._stop_processor.is_set():
            with self._update_lock:
                if self._pending_update is not None:
                    # Check if we should update now
                    if self._should_update_now():
                        blocks = self._pending_update
                        self._pending_update = None
                        self._update_canvas(blocks)
            
            # Check periodically
            self._stop_processor.wait(timeout=self.PROCESSOR_INTERVAL)
    
    def _cancel_pending_timer(self):
        """Cancel any pending timer."""
        with self._update_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
    
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
            True if update was triggered immediately, False if queued for debouncing
        """
        with self._update_lock:
            # Cancel any pending timer
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            
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
                
                self._update_canvas(blocks)
                return True
            else:
                # Queue update for later processing
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
                
                self._pending_update = blocks
                # Schedule a delayed update
                delay = self.DEBOUNCE_INTERVAL - (time.time() - self._last_update_time)
                self._timer = threading.Timer(delay, self._process_scheduled_update)
                self._timer.daemon = True
                self._timer.start()
                return False
    
    def _process_scheduled_update(self):
        """Process a scheduled pending update."""
        with self._update_lock:
            if self._pending_update is not None:
                blocks = self._pending_update
                self._pending_update = None
                self._update_canvas(blocks)
            self._timer = None
    
    def sync_canvas(self) -> str:
        """Force canvas synchronization.
        
        Returns:
            Canvas ID that was synced
        """
        # Cancel any pending timer to do immediate update
        with self._update_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_update = None
        
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
    
    def update_canvas_for_app(self, app_name: str) -> bool:
        """Update canvas for an entire app.
        
        Args:
            app_name: Application name
            
        Returns:
            True if update was triggered immediately, False if queued for debouncing
        """
        with self._update_lock:
            # Cancel any pending timer
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            
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
                self._update_canvas(blocks)
                return True
            else:
                self._pending_update = blocks
                # Schedule a delayed update
                delay = self.DEBOUNCE_INTERVAL - (time.time() - self._last_update_time)
                self._timer = threading.Timer(delay, self._process_scheduled_update)
                self._timer.daemon = True
                self._timer.start()
                return False
    
    def stop(self):
        """Stop the background processor thread."""
        self._stop_processor.set()
        with self._update_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_update = None
