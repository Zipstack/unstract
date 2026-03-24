from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Middleware to add Content-Security-Policy header to all responses.

    The policy is restrictive by default. The inline script in login.html
    is allowed via a SHA-256 hash rather than 'unsafe-inline' to maintain
    strong XSS protection. 'unsafe-inline' is only used for style-src
    because the login page uses inline <style> blocks.

    Uses response.setdefault() so that route-specific CSP policies set by
    views or earlier middleware are not overwritten.
    """

    # SHA-256 hash of the inline script in login.html (form submit spinner).
    # If that script changes, regenerate with:
    #   python -c "import hashlib,base64; ..."
    _SCRIPT_HASH = "sha256-GES82NvXpRYmVFDKv6vRHx2c7xuv8mgUzUaP7heKeFY="

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                f"script-src 'self' '{self._SCRIPT_HASH}'; "
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
