"""Tests for EPMPulse state management."""

import pytest
import os
import tempfile
import json
import fcntl
import threading
from pathlib import Path
from datetime import datetime

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.state.manager import StateManager, StateError
from src.state.models import State, App, Domain


class TestDomain:
    """Test Domain data class."""
    
    def test_domain_creation(self):
        """Test creating a Domain object."""
        domain = Domain(
            status='OK',
            job_id='JOB_001',
            message='Test message',
            updated='2026-02-16T12:00:00Z'
        )
        
        assert domain.status == 'OK'
        assert domain.job_id == 'JOB_001'
        assert domain.message == 'Test message'
        assert domain.duration_sec is None
    
    def test_domain_from_dict(self):
        """Test creating Domain from dictionary."""
        data = {
            'status': 'Loading',
            'job_id': 'LOAD_001',
            'message': None,
            'updated': '2026-02-16T12:00:00Z',
            'duration_sec': 45
        }
        
        domain = Domain.from_dict(data)
        
        assert domain.status == 'Loading'
        assert domain.job_id == 'LOAD_001'
        assert domain.duration_sec == 45


class TestApp:
    """Test App data class."""
    
    def test_app_creation(self):
        """Test creating an App object."""
        domains = {
            'Actual': Domain(status='OK', job_id='JOB_001'),
            'Budget': Domain(status='Loading', job_id='JOB_002')
        }
        
        app = App(
            name='Planning',
            display_name='Planning',
            domains=domains,
            channels=['C12345']
        )
        
        assert app.name == 'Planning'
        assert len(app.domains) == 2


class TestState:
    """Test State data class."""
    
    def test_state_creation(self):
        """Test creating a State object."""
        state = State(
            version='1.0',
            last_updated='2026-02-16T12:00:00Z'
        )
        
        assert state.version == '1.0'
        assert state.last_updated == '2026-02-16T12:00:00Z'
        assert len(state.apps) == 0
    
    def test_to_dict(self):
        """Test State to_dict conversion."""
        domains = {
            'Actual': Domain(status='OK', job_id='JOB_001')
        }
        apps = {
            'Planning': App(name='Planning', display_name='Planning', domains=domains)
        }
        
        state = State(
            version='1.0',
            last_updated='2026-02-16T12:00:00Z',
            apps=apps,
            metadata={}
        )
        
        result = state.to_dict()
        
        assert result['version'] == '1.0'
        assert 'Planning' in result['apps']
        assert result['last_updated'] == '2026-02-16T12:00:00Z'


class TestStateManager:
    """Test StateManager class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create StateManager with temp file."""
        state_file = temp_dir / 'test_state.json'
        return StateManager(state_file)
    
    def test_init_creates_file_if_missing(self, temp_dir):
        """Test StateManager creates file if it doesn't exist."""
        state_file = temp_dir / 'new_state.json'
        manager = StateManager(state_file)
        
        state = manager.read()
        
        assert state.version == '1.0'
        assert state.apps == {}
    
    def test_update_domain(self, manager):
        """Test updating a domain."""
        domain = manager.update(
            app_name='Planning',
            domain_name='Actual',
            status='Loading',
            job_id='LOAD_001'
        )
        
        assert domain.status == 'Loading'
        assert domain.job_id == 'LOAD_001'
        assert domain.updated is not None
    
    def test_get_all(self, manager):
        """Test getting all statuses."""
        manager.update('Planning', 'Actual', 'OK', 'JOB_001')
        manager.update('FCCS', 'Consolidation', 'Loading', 'JOB_002')
        
        result = manager.get_all()
        
        assert 'apps' in result
        assert 'Planning' in result['apps']
        assert 'FCCS' in result['apps']
        assert result['last_updated'] is not None
    
    def test_get_app(self, manager):
        """Test getting specific app status."""
        manager.update('Planning', 'Actual', 'OK', 'JOB_001')
        manager.update('Planning', 'Budget', 'Loading', 'JOB_002')
        
        result = manager.get_app('Planning')
        
        assert result['app'] == 'Planning'
        assert 'Actual' in result['domains']
        assert 'Budget' in result['domains']
    
    def test_atomic_write(self, manager):
        """Test atomic write creates temp file then renames."""
        manager.update('Planning', 'Actual', 'OK', 'JOB_001')
        
        state_file = manager.state_file
        assert state_file.exists()
        
        # Verify JSON structure
        with open(state_file, 'r') as f:
            data = json.load(f)
        
        assert 'version' in data
        assert 'apps' in data
        assert 'Planning' in data['apps']
    
    def test_concurrent_access(self, temp_dir):
        """Test file locking prevents corruption during concurrent updates."""
        state_file = temp_dir / 'concurrent_state.json'
        manager = StateManager(state_file)
        
        # Run multiple updates in parallel
        def update_domain(number):
            m = StateManager(state_file)
            for i in range(10):
                m.update('TestApp', f'Domain_{number}_{i}', 'OK', f'JOB_{number}_{i}')
        
        threads = [threading.Thread(target=update_domain, args=(i,)) for i in range(3)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify state file is still valid JSON
        with open(state_file, 'r') as f:
            data = json.load(f)
        
        assert 'apps' in data
        assert 'TestApp' in data['apps']


class TestStateContextManager:
    """Test StateManager context manager."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create StateManager with temp file."""
        state_file = tmp_path / 'context_state.json'
        return StateManager(state_file)
    
    def test_context_manager_enter_exit(self, manager):
        """Test context manager enters and exits correctly."""
        with manager as m:
            state = m.read()
            assert state is not None
    
    def test_context_manager_write(self, manager):
        """Test writing state in context manager."""
        with manager as m:
            state = m.read()
            domain = Domain(status='OK', job_id='JOB_001')
            state.add_domain('TestApp', 'TestDomain', domain)
            m.write(state)
        
        # Verify persistence
        with open(manager.state_file, 'r') as f:
            data = json.load(f)
        
        assert 'TestApp' in data['apps']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
