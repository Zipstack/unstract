class ToolRunException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ToolImageNotFoundError(ToolRunException):
    """Raised when a tool image is not found in the container registry."""

    # Error code for deterministic error identification across services
    ERROR_CODE = "TOOL_IMAGE_NOT_FOUND"

    def __init__(self, image_name: str, image_tag: str):
        self.image_name = image_name
        self.image_tag = image_tag
        self.message = (
            f"Tool image '{image_name}:{image_tag}' not found in container registry. "
            f"Please ensure the tool is properly deployed and the image exists."
        )
        super().__init__(self.message)
