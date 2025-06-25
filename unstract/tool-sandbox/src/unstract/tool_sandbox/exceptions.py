class ToolExecutionException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
