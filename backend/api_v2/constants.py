class ApiExecution:
    PATH: str = "deployment/api"
    MAXIMUM_TIMEOUT_IN_SEC: int = 300  # 5 minutes
    FILES_FORM_DATA: str = "files"
    TIMEOUT_FORM_DATA: str = "timeout"
    INCLUDE_METADATA: str = "include_metadata"
    INCLUDE_METRICS: str = "include_metrics"
    USE_FILE_HISTORY: str = "use_file_history"  # Undocumented parameter
