class NotFoundDestinationConfiguration(Exception):
    """Exception raised when destination configuration is not found."""

    def __init__(self, message="Destination configuration not found"):
        self.message = message
        super().__init__(self.message)


class NotFoundSourceConfiguration(Exception):
    """Exception raised when source configuration is not found."""

    def __init__(self, message="Source configuration not found"):
        self.message = message
        super().__init__(self.message)


class ExecutionException(Exception):
    """Exception raised when execution fails."""

    def __init__(self, message="Execution failed"):
        self.message = message
        super().__init__(self.message)
