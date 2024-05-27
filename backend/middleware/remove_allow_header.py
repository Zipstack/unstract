from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin


class RemoveAllowHeaderMiddleware(MiddlewareMixin):
    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.headers.pop("Allow", None)
        return response
