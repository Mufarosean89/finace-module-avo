"""
Audit middleware — logs API requests and their duration.
"""
import time
import logging

logger = logging.getLogger(__name__)


class AuditLogMiddleware:
    """Logs request method, path, status code, and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = int((time.time() - start) * 1000)

        if hasattr(response, 'status_code'):
            logger.info(
                '%s %s → %d (%dms)',
                request.method,
                request.path,
                response.status_code,
                duration,
            )

        return response
