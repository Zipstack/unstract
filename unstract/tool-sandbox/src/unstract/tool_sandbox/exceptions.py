class ToolExecutionException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ToolNotFoundInRegistryError(Exception):
    """Raised when a tool image is not found in the container registry.

    This indicates a platform configuration issue - the requested tool
    is not available in the container registry.
    """

    ERROR_CODE = "TOOL_IMAGE_NOT_FOUND"

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
