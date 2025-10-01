

class SdkError(Exception):
    DEFAULT_MESSAGE = "Something went wrong"
    actual_err: Exception | None = None
    status_code: int | None = None

    def __init__(
        self,
        message: str = DEFAULT_MESSAGE,
        status_code: int | None = None,
        actual_err: Exception | None = None,
    ) -> None:
        """Initialize the SdkError exception.

        Args:
            message: Error message description
            status_code: HTTP status code associated with the error
            actual_err: The original exception that caused this error
        """
        super().__init__(message)
        # Make it user friendly wherever possible
        self.message = message
        if actual_err:
            self.actual_err = actual_err

        # Setting status code for error
        if status_code:
            self.status_code = status_code
        elif actual_err:
            if hasattr(actual_err, "status_code"):  # Most providers
                self.status_code = actual_err.status_code
            elif hasattr(actual_err, "http_status"):  # Few providers like Mistral
                self.status_code = actual_err.http_status

    def __str__(self) -> str:
        """Return string representation of the SdkError."""
        return self.message


class IndexingError(SdkError):
    def __init__(self, message: str = "", **kwargs: object) -> None:
        """Initialize the IndexingError exception.

        Args:
            message: Error message description
            **kwargs: Additional keyword arguments passed to parent SdkError
        """
        if "404" in message:
            message = "Index not found. Please check vector DB settings."
        super().__init__(message, **kwargs)


class LLMError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to LLM"


class EmbeddingError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to embedding"


class VectorDBError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to vector DB"


class X2TextError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to text extractor"


class OCRError(SdkError):
    DEFAULT_MESSAGE = "Error ocurred related to OCR"


class RateLimitError(SdkError):
    DEFAULT_MESSAGE = "Running into rate limit errors, please try again later"


class FileStorageError(SdkError):
    DEFAULT_MESSAGE = (
        "Error while connecting with the storage. "
        "Please check the configuration credentials"
    )


class FileOperationError(SdkError):
    DEFAULT_MESSAGE = (
        "Error while performing operation on the file. "
        "Please check specific storage error for "
        "further information"
    )
