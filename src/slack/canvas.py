"""Canvas update manager with debouncing for EPMPulse."""

import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

from .client import SlackClient
from .blocks import build_app_block, build_canvas_state, build_single_domain_blocks


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
    
    def _update_canvas(self, blocks: list, is_full_sync: bool = False) -> bool:
        """Actually perform the canvas update.
        
        Args:
            blocks: Canvas blocks to set
            is_full_sync: If True, performs full document replace. If False,
                         attempts section-based update for rate limit efficiency.
            
        Returns:
            True if successful, False otherwise
        """
        if not self.slack_client.is_configured():
            print("Slack client not configured, skipping canvas update")
            return False
        
        # For full sync, use full document replace
        if is_full_sync:
            return self._update_full_canvas(blocks)
        
        # For partial updates, try section-based update first
        return self._update_section_based(blocks)
    
    def _update_full_canvas(self, blocks: list) -> bool:
        """Perform full canvas document replace.
        
        Args:
            blocks: Full canvas blocks to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            canvas_id = self._canvas_id
            
            # Update the entire canvas document
            self.slack_client.client.canvases_edit(
                canvas_id=canvas_id,
                document_json={'blocks': blocks}
            )
            
            self._last_update_time = time.time()
            return True
            
        except Exception as e:
            print(f"Full canvas update failed: {e}")
            return False
    
    def _update_section_based(self, blocks: list) -> bool:
        """Update specific sections of the canvas using canvases_section_update.
        
        Falls back to full canvas edit if section update fails or is not available.
        
        Args:
            blocks: Blocks containing section with block_id to update
            
        Returns:
            True if successful, False otherwise
        """
        # Find the first block with a block_id (the section we want to update)
        section_block = None
        for block in blocks:
            if block.get('block_id'):
                section_block = block
                break
        
        if not section_block:
            # No block_id found, fall back to full update
            return self._update_full_canvas(blocks)
        
        return self._update_section(self._canvas_id, [section_block])
    
    def _update_section(self, canvas_id: str, section_blocks: list) -> bool:
        """Update a specific canvas section using canvases_section_update.
        
        Args:
            canvas_id: Canvas ID to update
            section_blocks: Blocks with block_id to update
            
        Returns:
            True if successful, False otherwise
        """
        if not section_blocks:
            return False
        
        # Get the block_id from the first section block
        block_id = section_blocks[0].get('block_id')
        if not block_id:
            print("Section update failed: no block_id found in section blocks")
            return False
        
        try:
            # Try section-based update for rate limit efficiency
            if hasattr(self.slack_client, 'update_canvas_section'):
                success = self.slack_client.update_canvas_section(
                    canvas_id=canvas_id,
                    section_id=block_id,
                    blocks=section_blocks
                )
                if success:
                    self._last_update_time = time.time()
                    return True
            
            # Fall back to checking if client has canvases_section_update method
            if hasattr(self.slack_client.client, 'canvases_section_update'):
                self.slack_client.client.canvases_section_update(
                    canvas_id=canvas_id,
                    section_id=block_id,
                    blocks=section_blocks
                )
                self._last_update_time = time.time()
                return True
            else:
                print("Warning: canvases_section_update not available in Slack SDK, "
                      "falling back to full canvas edit")
                
                
        except Exception as e:
            error_msg = str(e)
            # Check if section doesn't exist yet (first-time setup)
            if 'section_not_found' in error_msg.lower() or 'not_found' in error_msg.lower():
                print(f"Section {block_id} not found, falling back to full canvas edit")
            else:
                print(f"Section update failed: {e}, falling back to full canvas edit")
        
        # Fall back to full canvas edit
        return self._update_full_canvas(section_blocks)
    
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
        """Update canvas for a specific domain using section-based update.
        
        Uses canvases_section_update for rate limit efficiency when possible.
        Falls back to full canvas edit if section doesn't exist.
        
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
            
            # Fetch state
            from ..state.manager import StateManager
            state_mgr = StateManager()
            state = state_mgr.read()
            
            # Build section blocks for this specific domain
            if app_name in state.apps:
                app = state.apps[app_name]
                domain = app.domains.get(domain_name)
                if domain:
                    # Use new function that adds proper block_ids
                    blocks = build_single_domain_blocks(
                        app_name=app_name,
                        display_name=app.display_name,
                        domain_name=domain_name,
                        domain_data=domain.to_dict()
                    )
                else:
                    # Fallback: create minimal blocks with proper block_id
                    blocks = [
                        {
                            'type': 'section',
                            'block_id': f"{app_name.lower()}_header",
                            'text': {'type': 'mrkdwn', 'text': f'*▸ {app_name}*'}
                        },
                        {
                            'type': 'section',
                            'block_id': f"{app_name.lower()}_{domain_name.lower()}_section",
                            'fields': [
                                {'type': 'mrkdwn', 'text': f'_{domain_name}_'},
                                {'type': 'mrkdwn', 'text': f'{self._get_status_icon(status)} {status}'}
                            ]
                        }
                    ]
            else:
                # Fallback: create minimal blocks with proper block_id
                blocks = [
                    {
                        'type': 'section',
                        'block_id': f"{app_name.lower()}_header",
                        'text': {'type': 'mrkdwn', 'text': f'*▸ {app_name}*'}
                    },
                    {
                        'type': 'section',
                        'block_id': f"{app_name.lower()}_{domain_name.lower()}_section",
                        'fields': [
                            {'type': 'mrkdwn', 'text': f'_{domain_name}_'},
                            {'type': 'mrkdwn', 'text': f'{self._get_status_icon(status)} {status}'}
                        ]
                    }
                ]
            
            if self._should_update_now():
                # Use section-based update (not full sync) for single domain updates
                self._update_canvas(blocks, is_full_sync=False)
                return True
            else:
                # Queue update for later processing
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
        """Force canvas synchronization (full document replace).
        
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
        # Full sync uses canvases_edit (document replace)
        self._update_canvas(blocks, is_full_sync=True)
        
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
        
        Note: App updates use section-based updates by default since they
        include proper block_ids. Each domain section will be updated individually
        for rate limit efficiency.
        
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
            
            # build_app_block now includes block_ids for section updates
            blocks = build_app_block(app_name, app.display_name, domains)
            
            if self._should_update_now():
                # Use section-based update (blocks have block_ids)
                self._update_canvas(blocks, is_full_sync=False)
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
