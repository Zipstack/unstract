class ApiExecution:
    PATH: str = "deployment/api"
    MAXIMUM_TIMEOUT_IN_SEC: int = 300  # 5 minutes
    FILES_FORM_DATA: str = "files"
    TIMEOUT_FORM_DATA: str = "timeout"
    INCLUDE_METADATA: str = "include_metadata"
