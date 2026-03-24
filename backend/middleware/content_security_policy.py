from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Middleware to add Content-Security-Policy header to all responses.

    The policy is restrictive by default. 'unsafe-inline' is required for
    script-src and style-src because the backend serves HTML pages (e.g.
    login.html) that contain inline scripts and styles.

    Uses response.setdefault() so that route-specific CSP policies set by
    views or earlier middleware are not overwritten.
    """

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self'; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
        )
        return response
