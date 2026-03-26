from unstract.connectors.exceptions import ConnectorError

S3FS_EXC_TO_UNSTRACT_EXC: dict[str, str] = {
    # Auth errors
    "The AWS Access Key Id you provided does not exist in our records": (
        "Invalid Key (Access Key ID) provided, please provide a valid one."
    ),
    "The request signature we calculated does not match the signature you provided": (
        "Invalid Secret (Secret Access Key) provided, please provide a valid one."
    ),
    "Unable to locate credentials": (
        "No AWS credentials found. Provide a valid access key/secret or ensure "
        "the instance/pod has an IAM role attached."
    ),
    "AssumeRoleWithWebIdentity": (
        "Failed to assume IAM role via web identity. Verify the IAM role exists "
        "and has the correct trust policy."
    ),
    "InvalidIdentityToken": (
        "The identity token provided is invalid. Verify the OIDC provider "
        "and ServiceAccount configuration."
    ),
    "ExpiredToken": (
        "AWS security token has expired. Refresh your credentials or ensure "
        "IAM role session duration is sufficient."
    ),
    # Permission errors
    "AccessDenied": (
        "Access denied. The IAM user or role does not have sufficient S3 "
        "permissions. Ensure the policy grants the required S3 actions "
        "(s3:ListAllMyBuckets, s3:ListBucket, s3:GetObject, s3:PutObject) "
        "on the target bucket."
    ),
    # Bucket errors
    "NoSuchBucket": (
        "The specified bucket does not exist. Please check the bucket name."
    ),
    # Endpoint / connectivity errors
    "[Errno 22] S3 API Requests must be made to API port": (  # Minio only
        "Request made to invalid port, please check the port of the endpoint URL."
    ),
    "Invalid endpoint": (
        "Could not connect to the endpoint URL. Please check if the URL is correct "
        "and accessible."
    ),
    "timed out": (
        "Connection timed out. Check network connectivity and the endpoint URL."
    ),
    "SSL: CERTIFICATE_VERIFY_FAILED": (
        "SSL certificate verification failed. If using a self-signed certificate "
        "(e.g. MinIO), check your endpoint configuration."
    ),
    "Name or service not known": (
        "Could not resolve the endpoint hostname. Please check the endpoint URL."
    ),
    # Clock / request errors
    "RequestTimeTooSkewed": (
        "The system clock is out of sync with AWS. Ensure the host's clock "
        "is accurate (max allowed skew is 15 minutes)."
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
