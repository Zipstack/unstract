from unstract.connectors.exceptions import ConnectorError

S3FS_EXC_TO_UNSTRACT_EXC_STATIC = {
    "The AWS Access Key Id you provided does not exist in our records": (
        "Invalid Key (Access Key ID) provided, please provide a valid one."
    ),
    "The request signature we calculated does not match the signature you provided": (
        "Invalid Secret (Secret Access Key) provided, please provide a valid one."
    ),
}

_AMBIENT_AUTH_MSG = (
    "AWS authentication failed — verify IAM role permissions "
    "or IRSA service account annotation."
)

S3FS_EXC_TO_UNSTRACT_EXC_AMBIENT = {
    "The AWS Access Key Id you provided does not exist in our records": _AMBIENT_AUTH_MSG,
    "The request signature we calculated does not match the signature you provided": (
        _AMBIENT_AUTH_MSG
    ),
}

S3FS_EXC_TO_UNSTRACT_EXC_COMMON = {
    "[Errno 22] S3 API Requests must be made to API port": (  # Minio only
        "Request made to invalid port, please check the port of the endpoint URL."
    ),
    "Invalid endpoint": (
        "Could not connect to the endpoint URL. Please check if the URL is correct "
        "and accessible."
    ),
}


def handle_s3fs_exception(
    e: Exception, using_static_creds: bool = True
) -> ConnectorError:
    """Parses the exception from S3/MinIO.

    Helps parse the S3/MinIO error and wraps it with our
    custom exception object to contain a user friendly message.

    Args:
        e (Exception): Error from S3/MinIO
        using_static_creds (bool): Whether static credentials were configured.
            Controls the auth error message style (key/secret vs IAM/IRSA).

    Returns:
        ConnectorError: Unstract's ConnectorError object
    """
    if isinstance(e, ConnectorError):
        return e

    original_exc = str(e)
    user_msg = "Error from S3 / MinIO while testing connection: "
    exc_to_append = ""

    # Choose auth-error mapping based on credential mode
    auth_map = (
        S3FS_EXC_TO_UNSTRACT_EXC_STATIC
        if using_static_creds
        else S3FS_EXC_TO_UNSTRACT_EXC_AMBIENT
    )

    # Check auth errors first, then common errors
    for exc_map in (auth_map, S3FS_EXC_TO_UNSTRACT_EXC_COMMON):
        for s3fs_exc, user_friendly_msg in exc_map.items():
            if s3fs_exc in original_exc:
                exc_to_append = user_friendly_msg
                break
        if exc_to_append:
            break

    # Generic error handling
    user_msg += (
        f"\n```\n{exc_to_append}\n```" if exc_to_append else f"\n```\n{str(e)}\n```"
    )
    return ConnectorError(message=user_msg)
