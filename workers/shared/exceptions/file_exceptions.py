"""File processing exception classes for workers.

This module defines exceptions related to file processing operations,
matching the backend's exception patterns.
"""


class UnsupportedMimeTypeError(Exception):
    """Exception raised when a file's MIME type is not supported.

    This exception is raised during file processing when a file's
    detected MIME type is not in the list of allowed types.
    """

    def __init__(self, message: str = "Unsupported MIME type"):
        """Initialize the exception with an error message.

        Args:
            message: Descriptive error message about the unsupported MIME type
        """
        self.message = message
        super().__init__(self.message)


class FileProcessingError(Exception):
    """Base exception class for file processing errors.

    This can be used as a base class for other file-related exceptions
    or raised directly for generic file processing issues.
    """

    def __init__(self, message: str = "File processing error occurred"):
        """Initialize the exception with an error message.

        Args:
            message: Descriptive error message about the file processing error
        """
        self.message = message
        super().__init__(self.message)


class EmptyFileError(FileProcessingError):
    """Exception raised when a file is empty (0 bytes).

    Empty files cannot be processed through workflows as they contain
    no meaningful content. This exception is raised to fail fast and
    provide clear feedback to users.
    """

    def __init__(self, file_path: str):
        """Initialize the exception with the empty file path.

        Args:
            file_path: Path to the empty file that caused the error
        """
        message = f"File is empty (0 bytes): {file_path}"
        super().__init__(message)
        self.file_path = file_path
