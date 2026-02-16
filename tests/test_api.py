"""Tests for EPMPulse API routes."""

import pytest
import os
import json
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.app import create_app
from src.config import get_api_key


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        os.environ['EPMPULSE_API_KEY'] = 'test_key_12345'
        app = create_app({'TESTING': True})
        return app.test_client()
    
    def test_health_returns_200(self, client):
        """Test health endpoint returns 200."""
        response = client.get('/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'


class TestAPIAuthentication:
    """Test API authentication."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        os.environ['EPMPULSE_API_KEY'] = 'test_key_12345'
        app = create_app({'TESTING': True})
        return app.test_client()
    
    def test_missing_auth_header(self, client):
        """Test request without auth header returns 401."""
        response = client.get('/api/v1/status')
        
        assert response.status_code == 401
        data = json.loads(response.data)
        assert data['success'] is False
        assert data['error']['code'] == 'MISSING_AUTH'
    
    def test_invalid_api_key(self, client):
        """Test request with invalid API key returns 403."""
        response = client.get(
            '/api/v1/status',
            headers={'Authorization': 'Bearer wrong_key'}
        )
        
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['error']['code'] == 'INVALID_KEY'
    
    def test_valid_api_key(self, client):
        """Test request with valid API key succeeds."""
        response = client.get(
            '/api/v1/status',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


class TestStatusEndpoints:
    """Test status CRUD endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        os.environ['EPMPULSE_API_KEY'] = 'test_key_12345'
        app = create_app({'TESTING': True})
        return app.test_client()
    
    def test_post_status(self, client):
        """Test POST /api/v1/status creates status."""
        payload = {
            'app': 'Planning',
            'domain': 'Actual',
            'status': 'Loading',
            'job_id': 'LOAD_001'
        }
        
        response = client.post(
            '/api/v1/status',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['app'] == 'Planning'
        assert data['data']['domain'] == 'Actual'
        assert data['data']['status'] == 'Loading'
    
    def test_post_status_invalid_app(self, client):
        """Test POST with invalid app returns error."""
        payload = {
            'app': 'InvalidApp',
            'domain': 'Actual',
            'status': 'OK'
        }
        
        response = client.post(
            '/api/v1/status',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error']['code'] == 'INVALID_APP'
    
    def test_post_status_invalid_status(self, client):
        """Test POST with invalid status returns error."""
        payload = {
            'app': 'Planning',
            'domain': 'Actual',
            'status': 'InvalidStatus'
        }
        
        response = client.post(
            '/api/v1/status',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error']['code'] == 'INVALID_STATUS'
    
    def test_get_all_statuses(self, client):
        """Test GET /api/v1/status returns all statuses."""
        # First create a status
        client.post(
            '/api/v1/status',
            data=json.dumps({
                'app': 'Planning',
                'domain': 'Actual',
                'status': 'OK',
                'job_id': 'JOB_001'
            }),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        # Then get all statuses
        response = client.get(
            '/api/v1/status',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'apps' in data['data']
    
    def test_get_app_status(self, client):
        """Test GET /api/v1/status/{app} returns specific app."""
        # Create a status
        client.post(
            '/api/v1/status',
            data=json.dumps({
                'app': 'Planning',
                'domain': 'Actual',
                'status': 'OK',
                'job_id': 'JOB_001'
            }),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        # Get specific app
        response = client.get(
            '/api/v1/status/Planning',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['app'] == 'Planning'
        assert 'domains' in data['data']
    
    def test_batch_update(self, client):
        """Test POST /api/v1/status/batch updates multiple."""
        payload = {
            'updates': [
                {
                    'app': 'Planning',
                    'domain': 'Actual',
                    'status': 'OK',
                    'job_id': 'FULL_001'
                },
                {
                    'app': 'FCCS',
                    'domain': 'Consolidation',
                    'status': 'OK',
                    'job_id': 'FULL_001'
                }
            ]
        }
        
        response = client.post(
            '/api/v1/status/batch',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'Authorization': 'Bearer test_key_12345'}
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['updated_count'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
