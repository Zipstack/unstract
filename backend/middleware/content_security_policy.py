from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Middleware to add Content-Security-Policy header to all responses.

    Since this is a JSON API backend, the policy is restrictive by default:
    only 'self' is allowed for all directives, and no inline scripts or styles
    are permitted. This prevents any injected content from being executed if a
    response is ever rendered in a browser context.
    """

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self'; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
        )
        return response
