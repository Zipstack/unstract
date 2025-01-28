class ToolNotFoundException(Exception):
    pass


class MissingToolIdException(Exception):
    pass


class ToolOutputNotFoundException(Exception):
    def __init__(self, message, error_code=404):
        super().__init__(message)
        self.error_code = error_code


class ToolParameterNotInExactFormat(Exception):
    pass


class InvalidToolPropertiesException(Exception):
    pass


class MissingConnectorException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


class MissingToolInstanceInputFormat(Exception):
    def __init__(self, message: str = "Input format not found") -> None:
        self.message = message


class BadRequestException(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


class ToolExecutionException(Exception):
    def __init__(self, message: str = "") -> None:
        self.message = message


class StopExecution(Exception):
    """This is a StopExecution exception while user stop the step execution."""

    def __init__(self, message: str = ""):
        super().__init__(message)


class MissingEnvVariable(Exception):
    pass


class ToolMetadataNotFound(Exception):
    def __init__(
        self, message: str = "Internal server error: Tool metadata not found."
    ) -> None:
        self.message = message
