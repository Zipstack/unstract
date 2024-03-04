
def RemoveAllowHeaderMiddleware(view_func):
    def wrapper(*args, **kwargs):
        response = view_func(*args, **kwargs)
        if 'Allow' in response:
            del response['Allow']
        return response
    return wrapper
