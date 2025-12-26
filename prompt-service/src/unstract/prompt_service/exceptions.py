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


class UnprocessableEntity(APIError):
    code = 422
    message = "Unprocessable Entity"


class CustomDataError(APIError):
    """Custom exception raised for errors with custom_data variables."""

    code = 400

    def __init__(self, variable: str, reason: str, is_ide: bool = True):
        if is_ide:
            help_text = "Please define this key in Prompt Studio Settings > Custom Data."
        else:
            help_text = (
                "Please include this key in the 'custom_data' field of your API request."
            )
        variable_display = "{{custom_data." + variable + "}}"
        message = (
            f"Custom data error for variable '{variable_display}': {reason} {help_text}"
        )
        super().__init__(message=message)
