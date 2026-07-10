"""
Request ID middleware — assigns a UUID to each request for tracing.
"""
import uuid


class RequestIDMiddleware:
    """Adds X-Request-Id header to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = request_id
        response = self.get_response(request)
        response['X-Request-Id'] = request_id
        return response
