"""Flask application factory for EPMPulse."""

from flask import Flask
from typing import Optional
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .config import get_api_key, get_config
from .api.routes import api_v1, set_limiter
from .api.errors import register_error_handlers


def create_app(test_config: Optional[dict] = None) -> Flask:
    """Create and configure the EPMPulse Flask application.
    
    Args:
        test_config: Optional test configuration dict
        
    Returns:
        Configured Flask application
        
    Raises:
        ValueError: If configuration validation fails (e.g., placeholder canvas IDs)
    """
    app = Flask(__name__, instance_relative_config=True)
    
    # Default configuration
    app.config.from_mapping(
        SECRET_KEY='dev',
        STATE_FILE='data/apps_status.json',
        MAX_CONTENT_LENGTH=16 * 1024,  # 16KB max request size
    )
    
    # Load test config if provided
    if test_config:
        app.config.update(test_config)
    
    # Load config from file if exists
    app.config.from_pyfile('config.py', silent=True)
    
    # Initialize Flask-Limiter (disabled in testing mode unless explicitly enabled)
    if not test_config or test_config.get('RATELIMIT_ENABLED', True):
        storage_uri = test_config.get('RATELIMIT_STORAGE_URI', "memory://") if test_config else "memory://"
        _limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["100 per minute"],  # Default: 100 reqs/min for all routes
            storage_uri=storage_uri,
            strategy="fixed-window",
            headers_enabled=True,
        )
        # Pass limiter to routes module for specific decorators
        set_limiter(_limiter)
    else:
        # Still set limiter to None so routes know it's disabled
        set_limiter(None)
    
    # Register API-blueprint
    app.register_blueprint(api_v1)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Health check at root (Flask-specific)
    @app.route('/health')
    def root_health():
        return {'status': 'healthy'}, 200
    
    return app


# Convenience import for direct app creation
app = create_app()
