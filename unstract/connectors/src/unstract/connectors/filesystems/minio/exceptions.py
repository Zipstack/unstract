from typing import NamedTuple

from unstract.connectors.exceptions import ConnectorError


class S3ErrorMessage(NamedTuple):
    """Maps an S3/MinIO error to user-friendly messages per auth mode.

    Attributes:
        static_msg: Message when using access key / secret credentials.
            None if the error is irrelevant for static credential mode.
        ambient_msg: Message when using IAM / IRSA credentials.
            None if the error is irrelevant for ambient credential mode.
    """

    static_msg: str | None
    ambient_msg: str | None


_AMBIENT_AUTH_MSG = (
    "AWS authentication failed — verify IAM role permissions "
    "or IRSA service account annotation."
)

_IRSA_NO_CREDS_MSG = (
    "No AWS credentials found. If running on EKS, ensure the pod's ServiceAccount "
    "is annotated with an IAM role ARN for IRSA. If running on EC2/ECS, ensure an "
    "IAM role is attached to the instance/task. Alternatively, provide static "
    "access key/secret."
)

_IRSA_ASSUME_ROLE_MSG = (
    "Failed to assume IAM role via web identity. Verify the IAM role exists, "
    "has the correct trust policy for the OIDC provider, and the identity "
    "(ServiceAccount, workload identity, etc.) is configured correctly."
)

_ACCESS_DENIED_MSG = (
    "Access denied — the IAM user or role does not have sufficient S3 "
    "permissions. Ensure the policy grants s3:ListAllMyBuckets (for connection "
    "test), s3:GetObject, s3:PutObject, s3:ListBucket, and s3:DeleteObject on "
    "the target bucket."
)

S3_ERROR_MAP: dict[str, S3ErrorMessage] = {
    # Auth errors — different messages for static vs ambient credentials
    "The AWS Access Key Id you provided does not exist in our records": S3ErrorMessage(
        static_msg="Invalid Key (Access Key ID) provided, please provide a valid one.",
        ambient_msg=_AMBIENT_AUTH_MSG,
    ),
    "The request signature we calculated does not match the signature you provided": (
        S3ErrorMessage(
            static_msg=(
                "Invalid Secret (Secret Access Key) provided,"
                " please provide a valid one."
            ),
            ambient_msg=_AMBIENT_AUTH_MSG,
        )
    ),
    # IAM/IRSA-only errors — no static equivalent
    "Unable to locate credentials": S3ErrorMessage(
        static_msg=None,
        ambient_msg=_IRSA_NO_CREDS_MSG,
    ),
    "AssumeRoleWithWebIdentity": S3ErrorMessage(
        static_msg=None,
        ambient_msg=_IRSA_ASSUME_ROLE_MSG,
    ),
    "InvalidIdentityToken": S3ErrorMessage(
        static_msg=None,
        ambient_msg=_IRSA_ASSUME_ROLE_MSG,
    ),
    # Common errors — same message regardless of auth mode
    "AccessDenied": S3ErrorMessage(
        static_msg=_ACCESS_DENIED_MSG,
        ambient_msg=_ACCESS_DENIED_MSG,
    ),
    "[Errno 22] S3 API Requests must be made to API port": S3ErrorMessage(  # Minio only
        static_msg=(
            "Request made to invalid port, please check the port of the endpoint URL."
        ),
        ambient_msg=(
            "Request made to invalid port, please check the port of the endpoint URL."
        ),
    ),
    "Invalid endpoint": S3ErrorMessage(
        static_msg=(
            "Could not connect to the endpoint URL. Please check if the URL is correct "
            "and accessible."
        ),
        ambient_msg=(
            "Could not connect to the endpoint URL. Please check if the URL is correct "
            "and accessible."
        ),
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

    for s3_exc, err_msg in S3_ERROR_MAP.items():
        if s3_exc in original_exc:
            msg = err_msg.static_msg if using_static_creds else err_msg.ambient_msg
            if msg:
                exc_to_append = msg
            break

    # Generic error handling
    user_msg += (
        f"\n```\n{exc_to_append}\n```" if exc_to_append else f"\n```\n{str(e)}\n```"
    )
    return ConnectorError(message=user_msg)
