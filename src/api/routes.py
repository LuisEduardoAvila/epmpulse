"""Flask routes for EPMPulse API."""

from flask import Blueprint, jsonify, request
from typing import Dict, Any, Optional
from datetime import datetime

from ..config import get_config, get_api_key
from ..state.manager import StateManager, StateError
from ..slack.client import SlackClient
from ..slack.canvas import CanvasManager
from .validators import StatusUpdateRequest, BatchStatusUpdateRequest
from .errors import error_response, ERROR_CODES

# Create API blueprint
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Global state manager
_state_manager = StateManager()

# Slack integration (initialized on first use)
_slack_client: Optional[SlackClient] = None
_canvas_manager: Optional[CanvasManager] = None


def _get_slack_client() -> SlackClient:
    """Get or initialize Slack client."""
    global _slack_client
    if _slack_client is None:
        _slack_client = SlackClient()
    return _slack_client


def _get_canvas_manager() -> CanvasManager:
    """Get or initialize Canvas manager."""
    global _canvas_manager
    if _canvas_manager is None:
        _canvas_manager = CanvasManager(_get_slack_client())
    return _canvas_manager


def _format_domain_response(domain):
    """Format Domain object for API response."""
    return {
        'app': None,  # Will be filled by caller
        'domain': None,  # Will be filled by caller
        'status': domain.status,
        'job_id': domain.job_id,
        'message': domain.message,
        'updated': domain.updated,
        'duration_sec': domain.duration_sec
    }


@api_v1.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    checks = {
        'state_file': 'ok',
        'slack_api': 'ok',
        'last_update': None
    }
    
    # Check state file
    try:
        state = _state_manager.get()
        checks['last_update'] = state.last_updated
    except StateError as e:
        checks['state_file'] = f'error: {str(e)}'
    
    # Check Slack connection
    try:
        client = _get_slack_client()
        if not client.is_configured():
            checks['slack_api'] = 'not_configured'
        else:
            # Simple test call
            client.test_connection()
            checks['slack_api'] = 'ok'
    except Exception as e:
        checks['slack_api'] = f'error: {str(e)}'
    
    all_healthy = all(v == 'ok' for v in checks.values() if v not in ['not_configured', checks['last_update']])
    
    return jsonify({
        'success': True,
        'data': {
            'status': 'healthy' if all_healthy else 'degraded',
            'checks': checks
        }
    }), 200


@api_v1.route('/status', methods=['POST'])
def update_status():
    """Update a single app/domain status."""
    # Validate API key
    api_key = request.headers.get('Authorization', '')
    if not api_key.startswith('Bearer '):
        return error_response('MISSING_AUTH', 'Missing Authorization header')
    
    key = api_key[7:]
    if key != get_api_key():
        return error_response('INVALID_KEY', 'Invalid API key')
    
    # Validate request
    try:
        data = request.get_json()
        if data is None:
            return error_response('INVALID_REQUEST', 'Invalid JSON payload')
        
        # Validate with Pydantic
        validated = StatusUpdateRequest(**data)
    except Exception as e:
        return error_response('INVALID_REQUEST', str(e))
    
    # Update state
    try:
        domain = _state_manager.update(
            app_name=validated.app,
            domain_name=validated.domain,
            status=validated.status,
            job_id=validated.job_id,
            message=validated.message,
            duration_sec=None
        )
        
        response_data = {
            'app': validated.app,
            'domain': validated.domain,
            'status': domain.status,
            'job_id': domain.job_id,
            'updated': domain.updated,
            'canvas_updated': False
        }
        
        # Update Slack canvas
        canvas_updated = False
        try:
            canvas_mgr = _get_canvas_manager()
            canvas_updated = canvas_mgr.update_canvas_for_domain(
                validated.app,
                validated.domain,
                validated.status
            )
            response_data['canvas_updated'] = canvas_updated
        except Exception as e:
            # Log warning but don't fail the request
            print(f"Warning: Canvas update failed: {e}")
        
        return jsonify({
            'success': True,
            'data': response_data
        }), 200
        
    except StateError as e:
        return error_response('STATE_ERROR', str(e))
    except Exception as e:
        return error_response('STATE_ERROR', f'Failed to update status: {str(e)}')


@api_v1.route('/status/batch', methods=['POST'])
def batch_update_status():
    """Update multiple app/domain statuses."""
    # Validate API key
    api_key = request.headers.get('Authorization', '')
    if not api_key.startswith('Bearer '):
        return error_response('MISSING_AUTH', 'Missing Authorization header')
    
    key = api_key[7:]
    if key != get_api_key():
        return error_response('INVALID_KEY', 'Invalid API key')
    
    # Validate request
    try:
        data = request.get_json()
        if data is None:
            return error_response('INVALID_REQUEST', 'Invalid JSON payload')
        
        # Validate with Pydantic
        validated = BatchStatusUpdateRequest(**data)
    except Exception as e:
        return error_response('INVALID_REQUEST', str(e))
    
    # Batch update
    try:
        result = _state_manager.batch_update([
            {
                'app': update.app,
                'domain': update.domain,
                'status': update.status,
                'job_id': update.job_id,
                'message': update.message
            }
            for update in validated.updates
        ])
        
        canvas_updated = False
        try:
            canvas_mgr = _get_canvas_manager()
            for update in validated.updates:
                canvas_mgr.update_canvas_for_domain(
                    update.app,
                    update.domain,
                    update.status
                )
            canvas_updated = True
        except Exception as e:
            print(f"Warning: Canvas update failed: {e}")
        
        return jsonify({
            'success': True,
            'data': {
                'updated_count': result['updated_count'],
                'updates': result['updates'],
                'canvas_updated': canvas_updated
            }
        }), 200
        
    except StateError as e:
        return error_response('STATE_ERROR', str(e))
    except Exception as e:
        return error_response('STATE_ERROR', f'Failed to batch update: {str(e)}')


@api_v1.route('/status', methods=['GET'])
def get_all_statuses():
    """Get all current statuses."""
    # Validate API key
    api_key = request.headers.get('Authorization', '')
    if not api_key.startswith('Bearer '):
        return error_response('MISSING_AUTH', 'Missing Authorization header')
    
    key = api_key[7:]
    if key != get_api_key():
        return error_response('INVALID_KEY', 'Invalid API key')
    
    # Get state
    try:
        result = _state_manager.get_all()
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except StateError as e:
        return error_response('STATE_ERROR', str(e))


@api_v1.route('/status/<app_name>', methods=['GET'])
def get_app_status(app_name: str):
    """Get status for a specific app."""
    # Validate API key
    api_key = request.headers.get('Authorization', '')
    if not api_key.startswith('Bearer '):
        return error_response('MISSING_AUTH', 'Missing Authorization header')
    
    key = api_key[7:]
    if key != get_api_key():
        return error_response('INVALID_KEY', 'Invalid API key')
    
    # Validate app name
    if app_name not in {'Planning', 'FCCS', 'ARCS'}:
        return error_response('INVALID_APP', 'App must be one of: Planning, FCCS, ARCS')
    
    # Get app status
    try:
        result = _state_manager.get_app(app_name)
        if result is None:
            return error_response('NOT_FOUND', f'App "{app_name}" not found')
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    except StateError as e:
        return error_response('STATE_ERROR', str(e))


@api_v1.route('/canvas/sync', methods=['POST'])
def sync_canvas():
    """Force canvas synchronization."""
    # Validate API key
    api_key = request.headers.get('Authorization', '')
    if not api_key.startswith('Bearer '):
        return error_response('MISSING_AUTH', 'Missing Authorization header')
    
    key = api_key[7:]
    if key != get_api_key():
        return error_response('INVALID_KEY', 'Invalid API key')
    
    try:
        canvas_mgr = _get_canvas_manager()
        canvas_id = canvas_mgr.sync_canvas()
        
        return jsonify({
            'success': True,
            'data': {
                'canvas_id': canvas_id,
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            }
        }), 200
    except Exception as e:
        return error_response('SLACK_ERROR', str(e))


# Convenience methods for direct import
def create_app():
    """Create Flask application with all routes registered."""
    from flask import Flask
    
    app = Flask(__name__)
    app.register_blueprint(api_v1)
    
    # Register error handlers
    from .errors import register_error_handlers
    register_error_handlers(app)
    
    return app
