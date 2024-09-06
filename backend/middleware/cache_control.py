from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class CacheControlMiddleware(MiddlewareMixin):
    """Middleware to add a Cache-Control header to all responses.

    This middleware sets the Cache-Control header to
    'max-age=0, no-cache, no-store, must-revalidate' to prevent caching.

    Methods:
        process_response(request, response): Adds the Cache-Control header.
    """

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response["Cache-Control"] = "max-age=0, no-cache, no-store, must-revalidate"
        return response
