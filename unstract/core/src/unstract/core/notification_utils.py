"""Shared notification utilities for Unstract platform.

This module contains notification processing utilities that can be used by both
backend Django services and worker processes for consistent notification handling.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import requests

from unstract.core.notification_enums import AuthorizationType

logger = logging.getLogger(__name__)

# Constants
APPLICATION_JSON = "application/json"


def serialize_notification_data(data: Any) -> Any:
    """Serialize notification data to handle UUIDs and datetimes.

    Args:
        data: Data to serialize (dict, list, or primitive)

    Returns:
        Serialized data safe for JSON encoding
    """
    if isinstance(data, UUID):
        return str(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, dict):
        return {k: serialize_notification_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_notification_data(item) for item in data]
    return data


def build_webhook_headers(
    authorization_type: str,
    authorization_key: str | None = None,
    authorization_header: str | None = None,
    custom_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build headers for webhook notifications based on authorization configuration.

    This function replicates the exact logic from the backend webhook implementation
    to maintain backward compatibility.

    Args:
        authorization_type: Type of authorization (BEARER, API_KEY, CUSTOM_HEADER, NONE)
        authorization_key: Authorization key/token
        authorization_header: Custom header name (for CUSTOM_HEADER type)
        custom_headers: Additional custom headers

    Returns:
        Dictionary of headers for the webhook request

    Raises:
        ValueError: If authorization configuration is invalid
    """
    headers = {"Content-Type": APPLICATION_JSON}

    # Add custom headers if provided
    if custom_headers:
        headers.update(custom_headers)

    try:
        auth_type = AuthorizationType(authorization_type.upper())
    except ValueError:
        raise ValueError(f"Unsupported authorization type: {authorization_type}")

    # Header format mapping - identical to backend implementation
    header_formats = {
        AuthorizationType.BEARER: lambda key: {
            "Authorization": f"Bearer {key}",
            "Content-Type": APPLICATION_JSON,
        },
        AuthorizationType.API_KEY: lambda key: {
            "Authorization": key,
            "Content-Type": APPLICATION_JSON,
        },
        AuthorizationType.CUSTOM_HEADER: lambda key: {
            authorization_header: key,
            "Content-Type": APPLICATION_JSON,
        },
        AuthorizationType.NONE: lambda _: {
            "Content-Type": APPLICATION_JSON,
        },
    }

    if auth_type not in header_formats:
        raise ValueError(f"Unsupported authorization type: {auth_type}")

    # Build authorization headers
    auth_headers = header_formats[auth_type](authorization_key)
    headers.update(auth_headers)

    # Validate custom header requirements
    if auth_type == AuthorizationType.CUSTOM_HEADER:
        if not authorization_header or not authorization_key:
            raise ValueError("Custom header or key missing for custom authorization.")

    return headers


def send_webhook_request(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    max_retries: int | None = None,
    retry_delay: int = 10,
    current_retry: int = 0,
) -> dict[str, Any]:
    """Send webhook request with retry logic.

    This function replicates the exact request logic from the backend webhook
    implementation to maintain backward compatibility.

    Args:
        url: Target webhook URL
        payload: JSON payload to send
        headers: HTTP headers
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries
        retry_delay: Delay between retries in seconds
        current_retry: Current retry attempt number

    Returns:
        Dictionary containing request result information

    Raises:
        requests.exceptions.RequestException: If request fails after all retries
    """
    # Serialize payload to handle UUIDs and datetimes
    serialized_payload = serialize_notification_data(payload)

    try:
        logger.debug(f"Sending webhook to {url} (attempt {current_retry + 1})")

        response = requests.post(
            url=url, json=serialized_payload, headers=headers or {}, timeout=timeout
        )

        # Check response status
        response.raise_for_status()

        if not (200 <= response.status_code < 300):
            error_msg = (
                f"Request to {url} failed with status code {response.status_code}. "
                f"Response: {response.text}"
            )
            logger.error(error_msg)
            raise requests.exceptions.HTTPError(error_msg, response=response)

        logger.info(
            f"Webhook sent successfully to {url} (status: {response.status_code})"
        )

        return {
            "success": True,
            "status_code": response.status_code,
            "response_text": response.text,
            "attempts": current_retry + 1,
            "url": url,
        }

    except requests.exceptions.RequestException as exc:
        # Handle retries - exact logic from backend implementation
        if max_retries is not None and current_retry < max_retries:
            logger.warning(
                f"Request to {url} failed. Retrying in {retry_delay} seconds. "
                f"Attempt {current_retry + 1}/{max_retries}. Error: {exc}"
            )

            # For worker implementation, we'll raise with retry info
            # The worker retry mechanism will handle the delay
            raise exc
        else:
            error_msg = (
                f"Failed to send webhook to {url} after {max_retries or 1} attempts. "
                f"Error: {exc}"
            )
            logger.error(error_msg)

            return {
                "success": False,
                "error": str(exc),
                "attempts": current_retry + 1,
                "url": url,
            }


def validate_webhook_data(
    url: str | None,
    payload: dict[str, Any] | None,
    authorization_type: str | None = None,
    authorization_key: str | None = None,
    authorization_header: str | None = None,
) -> bool:
    """Validate webhook notification data.

    Args:
        url: Webhook URL
        payload: Notification payload
        authorization_type: Authorization type
        authorization_key: Authorization key
        authorization_header: Custom authorization header name

    Returns:
        True if validation passes

    Raises:
        ValueError: If validation fails
    """
    if not url:
        raise ValueError("Webhook URL is required.")

    if not payload:
        raise ValueError("Payload is required.")

    # Validate authorization configuration if provided
    if authorization_type:
        try:
            auth_type = AuthorizationType(authorization_type.upper())

            # Check custom header requirements
            if auth_type == AuthorizationType.CUSTOM_HEADER:
                if not authorization_header or not authorization_key:
                    raise ValueError(
                        "Custom header or key missing for custom authorization."
                    )

        except ValueError:
            raise ValueError(f"Unsupported authorization type: {authorization_type}")

    return True


def format_notification_error(
    error: Exception, notification_type: str, destination: str, attempt: int = 1
) -> str:
    """Format notification error message consistently.

    Args:
        error: Exception that occurred
        notification_type: Type of notification (WEBHOOK, EMAIL, etc.)
        destination: Target destination (URL, email, etc.)
        attempt: Attempt number

    Returns:
        Formatted error message
    """
    return (
        f"{notification_type} notification failed to {destination} "
        f"(attempt {attempt}): {str(error)}"
    )
