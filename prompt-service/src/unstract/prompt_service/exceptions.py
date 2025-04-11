from unstract.core.flask.exceptions import APIError


class BadRequest(APIError):
    code = 400
    message = "Bad Request / No payload"


class RateLimitError(APIError):
    code = 429
    message = "Running into rate limit errors, please try again later"


class MissingFieldError(APIError):
    """Custom error for missing fields."""

    def __init__(self, missing_fields: list[str]):
        message = f"Missing required fields: {', '.join(missing_fields)}"
        super().__init__(message=message)


class RetrievalError(APIError):
    """Custom exception raised for errors during retrieval from VectorDB."""

    DEFAULT_MESSAGE = (
        "Error while retrieving data from the VectorDB. "
        "Please contact the admin for further assistance."
    )


class ExtractionError(APIError):
    DEFAULT_MESSAGE = "Error while extracting from a document"
