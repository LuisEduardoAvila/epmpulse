"""Tests for CanvasManager debouncing behavior."""

import pytest
import time
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestCanvasDebouncing:
    """Test CanvasManager debouncing behavior."""
    
    @pytest.fixture
    def canvas_manager(self):
        """Create CanvasManager."""
        os.environ['SLACK_MAIN_CANVAS_ID'] = 'F1234567890'
        
        from src.slack.canvas import CanvasManager
        
        # Create CanvasManager without mocking - will use real Slack client
        # which may fail but that's ok for this test
        cm = CanvasManager()
        yield cm
        cm.stop()
    
    def test_process_pending_loop_exists(self, canvas_manager):
        """Test that _process_pending_loop method exists."""
        assert hasattr(canvas_manager, '_process_pending_loop')
        assert callable(getattr(canvas_manager, '_process_pending_loop'))
    
    def test_cancel_pending_timer_method_exists(self, canvas_manager):
        """Test that _cancel_pending_timer method exists."""
        assert hasattr(canvas_manager, '_cancel_pending_timer')
        assert callable(getattr(canvas_manager, '_cancel_pending_timer'))
    
    def test_stop_method_exits_cleanly(self, canvas_manager):
        """Test that stop method properly shuts down the processor."""
        # Stop should not raise
        canvas_manager.stop()
        
        # Processor should be stopped
        assert canvas_manager._stop_processor.is_set()
    
    def test_pending_update_cleared_on_stop(self, canvas_manager):
        """Test that pending update is cleared on stop."""
        canvas_manager._pending_update = {'test': 'data'}
        canvas_manager.stop()
        
        # Pending update should be cleared
        assert canvas_manager._pending_update is None
    
    def test_debounce_interval_constant(self, canvas_manager):
        """Test that DEBOUNCE_INTERVAL is set correctly."""
        assert canvas_manager.DEBOUNCE_INTERVAL == 2.0
    
    def test_processor_interval_constant(self, canvas_manager):
        """Test that PROCESSOR_INTERVAL is set correctly."""
        assert canvas_manager.PROCESSOR_INTERVAL == 0.5
    
    def test_lock_created(self, canvas_manager):
        """Test that update lock is created."""
        assert hasattr(canvas_manager, '_update_lock')
    
    def test_timer_initially_none(self, canvas_manager):
        """Test that timer is initially None."""
        assert canvas_manager._timer is None
    
    def test_pending_update_initially_none(self, canvas_manager):
        """Test that pending_update is initially None."""
        assert canvas_manager._pending_update is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
