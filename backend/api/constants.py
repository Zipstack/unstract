class ApiExecution:
    PATH: str = "deployment/api"
    MAXIMUM_TIMEOUT_IN_SEC: int = 300  # 5 minutes
    DEFAULT_TIMEOUT_IN_SEC: int = 80
    FILES_FORM_DATA: str = "files"
    TIMEOUT_FORM_DATA: str = "timeout"
