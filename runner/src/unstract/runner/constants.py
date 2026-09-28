class LogType:
    LOG = "LOG"
    UPDATE = "UPDATE"
    COST = "COST"
    RESULT = "RESULT"
    SINGLE_STEP = "SINGLE_STEP_MESSAGE"


class LogLevel:
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"


class ToolKey:
    TOOL_INSTANCE_ID = "tool_instance_id"


class Env:
    TOOL_CONTAINER_NETWORK = "TOOL_CONTAINER_NETWORK"
    TOOL_CONTAINER_LABELS = "TOOL_CONTAINER_LABELS"
    PRIVATE_REGISTRY_CREDENTIAL_PATH = "PRIVATE_REGISTRY_CREDENTIAL_PATH"
    PRIVATE_REGISTRY_USERNAME = "PRIVATE_REGISTRY_USERNAME"
    PRIVATE_REGISTRY_URL = "PRIVATE_REGISTRY_URL"
    LOG_LEVEL = "LOG_LEVEL"
    REMOVE_CONTAINER_ON_EXIT = "REMOVE_CONTAINER_ON_EXIT"
    WORKFLOW_EXECUTION_DIR_PREFIX = "WORKFLOW_EXECUTION_DIR_PREFIX"
    WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS = (
        "WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS"
    )
    EXECUTION_DATA_DIR = "EXECUTION_DATA_DIR"
    FLIPT_SERVICE_AVAILABLE = "FLIPT_SERVICE_AVAILABLE"
    TOOL_SIDECAR_ENABLED = "TOOL_SIDECAR_ENABLED"
    TOOL_SIDECAR_IMAGE_NAME = "TOOL_SIDECAR_IMAGE_NAME"
    TOOL_SIDECAR_CONTAINER_WAIT_TIMEOUT = "TOOL_SIDECAR_CONTAINER_WAIT_TIMEOUT"
    TOOL_SIDECAR_IMAGE_TAG = "TOOL_SIDECAR_IMAGE_TAG"
    REDIS_HOST = "REDIS_HOST"
    REDIS_PORT = "REDIS_PORT"
    REDIS_USER = "REDIS_USER"
    REDIS_PASSWORD = "REDIS_PASSWORD"
    REDIS_SENTINEL_MODE = "REDIS_SENTINEL_MODE"
    REDIS_SENTINEL_MASTER_NAME = "REDIS_SENTINEL_MASTER_NAME"
    # UN-4123. Same allowlist trap as LOG_TRANSPORT below: the sidecar publishes tool
    # logs through LogPublisher and builds its own Redis client, so without these it
    # would keep connecting in PLAINTEXT to db 0 while every other process moved to
    # TLS — a connection failure at best, and tool logs silently absent at worst.
    REDIS_DB = "REDIS_DB"
    REDIS_SSL = "REDIS_SSL"
    REDIS_SSL_CERT_REQS = "REDIS_SSL_CERT_REQS"
    # Forwarded as a PATH, and nothing mounts a CA into the sidecar: only the
    # shared logs volume is. It therefore works only for an image that bakes the
    # CA in at this path — otherwise load_verify_locations() raises on a file
    # that is not there. Kept forwarded so the baked-in case is configurable;
    # the caveat is spelled out in runner/sample.env.
    REDIS_SSL_CA_CERTS = "REDIS_SSL_CA_CERTS"
    # The ONLY way back from the on-by-default hostname verification that UN-4123
    # introduced. An endpoint whose certificate SAN does not match how it is
    # addressed (an IP, an internal CNAME) needs it set to false platform-wide —
    # and without it here, these processes alone would keep verifying and fail the
    # handshake while everything else recovered.
    REDIS_SSL_CHECK_HOSTNAME = "REDIS_SSL_CHECK_HOSTNAME"
    REDIS_URL = "REDIS_URL"
    # Read by _resolve_health_check_interval in this same client, so the
    # documented "set it to 0 to restore the old behaviour" lever has to reach
    # here too — otherwise these processes silently keep the 30s default.
    REDIS_HEALTH_CHECK_INTERVAL = "REDIS_HEALTH_CHECK_INTERVAL"
    CELERY_BROKER_BASE_URL = "CELERY_BROKER_BASE_URL"
    CELERY_BROKER_USER = "CELERY_BROKER_USER"
    CELERY_BROKER_PASS = "CELERY_BROKER_PASS"
    # Log-streaming transport (UN-3755). Must reach the SIDECAR: it is the process
    # that calls LogPublisher.publish for tool logs
    # (tool_sidecar/log_processor.py:165), and the sidecar's environment is a
    # hand-picked allowlist rather than an inherited one — so anything absent here is
    # silently absent there, and it falls back to publishing on Celery/RabbitMQ.
    LOG_TRANSPORT = "LOG_TRANSPORT"
    LOG_STREAM_QUEUE_NAME = "LOG_STREAM_QUEUE_NAME"
