class FilesystemError(Exception):
    """Base exception class for filesystem-related errors."""

    default_message = "An error occurred in the filesystem operation."

    def __init__(self, message: str = None):
        self.message = message or self.default_message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ProviderNotFound(FilesystemError):
    default_message = "The requested provider was not found."
