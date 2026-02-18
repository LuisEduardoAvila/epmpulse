"""Decorators for EPMPulse utility functions."""

import time
import functools
import threading
from typing import Optional, List, Callable, Any
from datetime import datetime
from flask import request, jsonify
from functools import wraps


def require_api_key(f: Callable) -> Callable:
    """Decorator to require API key authentication.
    
    Args:
        f: Function to decorate
        
    Returns:
        Decorated function
    """
    from ..config import get_api_key
    
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('Authorization', '')
        
        if not api_key.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': {
                    'code': 'MISSING_AUTH',
                    'message': 'Missing Authorization header'
                }
            }), 401
        
        key = api_key[7:]
        try:
            expected_key = get_api_key()
        except ValueError:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'CONFIG_ERROR',
                    'message': 'API key not configured'
                }
            }), 500
        
        if key != expected_key:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'INVALID_KEY',
                    'message': 'Invalid API key'
                }
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated


def retry(
    max_attempts: int = 3,
    backoff_seconds: Optional[List[float]] = None,
    exceptions: tuple = (Exception,)
) -> Callable:
    """Decorator to retry function on specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts
        backoff_seconds: List of delays between attempts
        exceptions: Tuple of exception types to catch
        
    Returns:
        Decorated function
    """
    backoff_seconds = backoff_seconds or [1, 2, 4]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        delay = backoff_seconds[attempt % len(backoff_seconds)]
                        time.sleep(delay)
                    else:
                        raise
            
            raise last_exception
        
        return wrapper
    
    return decorator


class Debouncer:
    """Debouncer for rate limiting function calls."""
    
    def __init__(self, min_interval: float = 2.0):
        """Initialize debouncer.
        
        Args:
            min_interval: Minimum seconds between calls
        """
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
    
    def should_call(self) -> bool:
        """Check if function should be called.
        
        Returns:
            True if should call, False if should defer
        """
        with self._lock:
            current_time = time.time()
            return (current_time - self._last_call) >= self.min_interval
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function if debouncer allows.
        
        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result or None if not called
        """
        if self.should_call():
            result = func(*args, **kwargs)
            self._last_call = time.time()
            return result
        return None


# Decorator version for functions
def debounce(min_interval: float = 2.0) -> Callable:
    """Decorator to debounce function calls.
    
    Args:
        min_interval: Minimum seconds between calls
        
    Returns:
        Decorated function
    """
    debouncer = Debouncer(min_interval)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return debouncer.call(func, *args, **kwargs)
        
        return wrapper
    
    return decorator
