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
}


def handle_s3fs_exception(e: Exception) -> ConnectorError:
    original_exc = str(e)
    user_msg = "Error while connecting to S3 / MinIO: "
    exc_to_append = ""
    for s3fs_exc, user_friendly_msg in S3FS_EXC_TO_UNSTRACT_EXC.items():
        if s3fs_exc in original_exc:
            exc_to_append = user_friendly_msg
            break

    user_msg += exc_to_append if exc_to_append else f"Error from S3, '{str(e)}'"
    return ConnectorError(message=user_msg)
