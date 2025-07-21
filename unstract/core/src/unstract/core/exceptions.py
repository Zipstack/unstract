class ToolExecutionStatusException(Exception):
    """Raised when an invalid tool execution status is provided."""

    def __init__(self, message: str = "Invalid tool execution status"):
        super().__init__(message)


class ToolExecutionValueException(Exception):
    """Raised when required execution identifiers are missing."""

    def __init__(self, message: str = "Execution ID and file execution ID are required"):
        super().__init__(message)


class FileExecutionTrackerValueException(Exception):
    """Raised when required execution identifiers are missing."""

    def __init__(self, message: str = "Execution ID and file execution ID are required"):
        super().__init__(message)


class FileExecutionTrackerNotFound(Exception):
    """Raised when FileExecutionTracker is not found."""

    def __init__(self, message: str = "FileExecutionTracker not found"):
        super().__init__(message)


class FileExecutionStageException(Exception):
    """Raised when an invalid file execution stage is provided."""

    def __init__(self, message: str = "Invalid file execution stage"):
        super().__init__(message)
