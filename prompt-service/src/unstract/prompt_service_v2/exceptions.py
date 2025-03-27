from unstract.core.flask.exceptions import APIError


class NoPayloadError(APIError):
    code = 400
    message = "Bad Request / No payload"


class RateLimitError(APIError):
    code = 429
    message = "Running into rate limit errors, please try again later"
