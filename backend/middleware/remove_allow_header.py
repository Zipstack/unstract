from django.utils.deprecation import MiddlewareMixin


class RemoveAllowHeaderMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        response.headers.pop('Allow', None)
        return response
