"""Logging configuration for Kairon backend.

Provides structured logging with request/response tracking,
timing, and error reporting.
"""
import logging
import time
from functools import wraps
from flask import request, g

logger = logging.getLogger(__name__)


def setup_logging(app):
    """Configure Flask app logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Hook before/after request for timing & logging
    @app.before_request
    def before_request():
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        elapsed = time.time() - g.start_time
        status_code = response.status_code
        method = request.method
        path = request.path
        remote_addr = request.remote_addr

        # Determine log level based on status
        if 200 <= status_code < 300:
            log_level = logging.INFO
            status_emoji = "✓"
        elif 300 <= status_code < 400:
            log_level = logging.INFO
            status_emoji = "→"
        elif 400 <= status_code < 500:
            log_level = logging.WARNING
            status_emoji = "⚠"
        else:
            log_level = logging.ERROR
            status_emoji = "✗"

        message = (
            f"{status_emoji} {method:4} {path:30} | "
            f"Status: {status_code} | "
            f"Duration: {elapsed:.2f}s | "
            f"IP: {remote_addr}"
        )

        logger.log(log_level, message)

        return response


def log_endpoint(name=None):
    """Decorator to add custom logging to endpoints."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            endpoint_name = name or f.__name__
            try:
                result = f(*args, **kwargs)
                logger.debug(f"Endpoint '{endpoint_name}' executed successfully.")
                return result
            except Exception as e:
                logger.error(f"Endpoint '{endpoint_name}' failed: {str(e)}")
                raise
        return decorated_function
    return decorator
