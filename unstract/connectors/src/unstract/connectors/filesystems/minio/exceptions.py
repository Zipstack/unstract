from unstract.connectors.exceptions import ConnectorError

S3FS_EXC_TO_UNSTRACT_EXC = {
    "The AWS Access Key Id you provided does not exist in our records": (
        "Invalid Key (Access Key ID) provided, please provide a valid one."
    ),
    "The request signature we calculated does not match the signature you provided": (
        "Invalid Secret (Secret Access Key) provided, please provide a valid one."
    ),
    "[Errno 22] S3 API Requests must be made to API port": (  # Minio only
        "Request made to invalid port, please check the port of the endpoint URL."
    ),
    "Invalid endpoint": (
        "Could not connect to the endpoint URL. Please check if the URL is correct "
        "and accessible."
    ),
}


def handle_s3fs_exception(e: Exception) -> ConnectorError:
    """Parses the exception from S3/MinIO.

    Helps parse the S3/MinIO error and wraps it with our
    custom exception object to contain a user friendly message.

    Args:
        e (Exception): Error from S3/MinIO

    Returns:
        ConnectorError: Unstract's ConnectorError object
    """
    if isinstance(e, ConnectorError):
        return e

    original_exc = str(e)
    user_msg = "Error from S3 / MinIO while testing connection: "
    exc_to_append = ""
    for s3fs_exc, user_friendly_msg in S3FS_EXC_TO_UNSTRACT_EXC.items():
        if s3fs_exc in original_exc:
            exc_to_append = user_friendly_msg
            break

    # Generic error handling
    user_msg += (
        f"\n```\n{exc_to_append}\n```" if exc_to_append else f"\n```\n{str(e)}\n```"
    )
    return ConnectorError(message=user_msg)
