class CustomException(Exception):
    def __init__(self, message: str = "An error occurred", code: int = 500) -> None:
        self.message = message
        self.code = code
        super().__init__(self.message)
