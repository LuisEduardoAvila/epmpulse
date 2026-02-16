"""Logging configuration for EPMPulse with structured JSON output."""

import logging
import json
import sys
import os
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.
        
        Args:
            record: LogRecord to format
            
        Returns:
            JSON string
        """
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(
    level: Optional[str] = None,
    handler: Optional[logging.Handler] = None
) -> logging.Logger:
    """Setup EPMPulse logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        handler: Custom handler (uses JSONFormatter by default)
        
    Returns:
        Configured logger instance
    """
    # Get level from env or use INFO
    log_level = level or os.environ.get('LOG_LEVEL', 'INFO')
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger('epmpulse')
    logger.setLevel(log_level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create formatter
    formatter = JSONFormatter()
    
    # Create handler
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
    
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str = 'epmpulse') -> logging.Logger:
    """Get a logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Convenience function for adding extra fields
def log_with_fields(
    logger: logging.Logger,
    level: str,
    message: str,
    **fields
):
    """Log with extra fields.
    
    Args:
        logger: Logger instance
        level: Log level name
        message: Log message
        **fields: Extra fields to include
    """
    extra = {'extra_fields': fields} if fields else None
    
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=extra)
