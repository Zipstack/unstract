from functools import wraps


class RemoveAllowHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if 'Allow' in response:
            del response['Allow']
        return response

    def remove_allow_header(self):
        @wraps(self)
        def wrapper(*args, **kwargs):
            response = self(*args, **kwargs)
            if 'Allow' in response:
                del response['Allow']
            return response
        return wrapper
