"""Error handlers and response formatters for EPMPulse API."""

from flask import jsonify
from typing import Dict, Any


def error_response(code: str, message: str, details: Dict[str, Any] = None, status_code: int = None) -> tuple:
    """Create standard error response.
    
    Args:
        code: Error code (e.g., 'INVALID_STATUS')
        message: Human-readable error message
        details: Optional additional details
        status_code: HTTP status code (uses ERROR_CODES mapping if not provided)
        
    Returns:
        Tuple of (json response, status code)
    """
    # Get status code from ERROR_CODES if not provided
    if status_code is None and code in ERROR_CODES:
        status_code = ERROR_CODES[code].get('status', 400)
    elif status_code is None:
        status_code = 400
    
    response = {
        'success': False,
        'error': {
            'code': code,
            'message': message
        }
    }
    
    if details:
        response['error']['details'] = details
    
    return jsonify(response), status_code


# HTTP Status Codes mapping
HTTP_STATUS_CODES = {
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not Found',
    422: 'Unprocessable Entity',
    429: 'Too Many Requests',
    500: 'Internal Server Error',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
}


# Error code definitions
ERROR_CODES = {
    'MISSING_AUTH': {
        'message': 'Missing or invalid Authorization header',
        'status': 401,
    },
    'INVALID_KEY': {
        'message': 'Invalid API key',
        'status': 403,
    },
    'INVALID_STATUS': {
        'message': 'Status must be one of: Blank, Loading, OK, Warning',
        'status': 400,
    },
    'INVALID_APP': {
        'message': 'App must be one of: Planning, FCCS, ARCS',
        'status': 400,
    },
    'STATE_ERROR': {
        'message': 'State file read/write error',
        'status': 500,
    },
    'SLACK_ERROR': {
        'message': 'Slack API call failed',
        'status': 502,
    },
    'RATE_LIMITED': {
        'message': 'Rate limit exceeded',
        'status': 429,
    },
    'INVALID_REQUEST': {
        'message': 'Invalid request payload',
        'status': 400,
    },
    'NOT_FOUND': {
        'message': 'Resource not found',
        'status': 404,
    },
}


def register_error_handlers(app):
    """Register custom error handlers with Flask app.
    
    Args:
        app: Flask application instance
    """
    
    @app.errorhandler(400)
    def bad_request(error):
        return error_response(
            'INVALID_REQUEST',
            'Bad request',
            {'description': str(error.description)}
        )
    
    @app.errorhandler(401)
    def unauthorized(error):
        return error_response(
            'MISSING_AUTH',
            'Missing or invalid Authorization header'
        )
    
    @app.errorhandler(403)
    def forbidden(error):
        return error_response(
            'INVALID_KEY',
            'Invalid API key'
        )
    
    @app.errorhandler(404)
    def not_found(error):
        return error_response(
            'NOT_FOUND',
            'Resource not found'
        )
    
    @app.errorhandler(429)
    def rate_limited(error):
        return error_response(
            'RATE_LIMITED',
            'Rate limit exceeded'
        )
    
    @app.errorhandler(500)
    def internal_error(error):
        return error_response(
            'STATE_ERROR',
            'Internal server error'
        )
    
    @app.errorhandler(502)
    def bad_gateway(error):
        return error_response(
            'SLACK_ERROR',
            'Slack API call failed'
        )
