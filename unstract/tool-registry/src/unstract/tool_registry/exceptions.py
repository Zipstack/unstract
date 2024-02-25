class InvalidToolURLException(Exception):
    pass


class InvalidToolProperties(Exception):
    pass


class RegistryNotFound(Exception):
    pass


class DuplicateURLException(Exception):
    pass


class BuildAndRunException(Exception):
    pass


class InvalidSchemaInput(Exception):
    def __init__(self, message: str = "Invalid input data") -> None:
        self.message = message
        super().__init__(self.message)
