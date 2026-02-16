"""Flask application factory for EPMPulse."""

from flask import Flask
from typing import Optional

from .config import get_api_key, get_config
from .api.routes import api_v1
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
