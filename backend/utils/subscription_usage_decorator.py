"""Decorator and utilities for automatic subscription usage tracking.

This module provides a decorator to automatically handle subscription usage
commit/discard operations, reducing boilerplate code and ensuring consistent
behavior across the codebase.
"""

import functools
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from plugins import get_plugin

from utils.user_session import UserSessionUtils

logger = logging.getLogger(__name__)


def track_subscription_usage_if_available(
    file_execution_id_param: str,
    org_id_param: str = "org_id",
    extract_from_request: bool = False,
) -> Callable:
    """Decorator to automatically track subscription usage.

    Automatically commits subscription usage on successful function execution
    and discards it on failure. This eliminates repetitive try/except blocks
    for subscription tracking.

    Args:
        file_execution_id_param: Name of the parameter containing file_execution_id
        org_id_param: Name of the parameter containing org_id (default: "org_id")
        extract_from_request: If True, extracts org_id from Django request object
                            using UserSessionUtils.get_organization_id()

    Returns:
        Decorated function

    Example:
        @track_subscription_usage_if_available(file_execution_id_param="run_id", extract_from_request=True)
        def index_document(self, request, pk=None):
            # Your code here - subscription usage tracked automatically
            return result

    Note:
        - Subscription tracking errors are logged but don't affect main function
        - If identifiers are missing, tracking is silently skipped
        - Works with both regular functions and Django view methods
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract file_execution_id
            file_execution_id = kwargs.get(file_execution_id_param)

            # Extract org_id
            if extract_from_request:
                # Handle both function(request) and method(self, request) patterns
                request = kwargs.get("request")
                if not request and len(args) >= 2:
                    # Assume args[0] is self, args[1] is request for methods
                    request = args[1]
                elif not request and len(args) >= 1 and "self" not in kwargs:
                    # Assume args[0] is request for functions
                    request = args[0]

                if request:
                    org_id = UserSessionUtils.get_organization_id(request)
                else:
                    org_id = None
                    logger.warning(
                        f"Could not extract request object in {func.__name__}, "
                        "subscription tracking skipped"
                    )
            else:
                org_id = kwargs.get(org_id_param)

            # Skip tracking if identifiers are missing
            if not file_execution_id or not org_id:
                logger.debug(
                    f"Skipping subscription tracking in {func.__name__}: "
                    f"file_execution_id={file_execution_id}, org_id={org_id}"
                )
                return func(*args, **kwargs)

            try:
                # Execute main function
                result = func(*args, **kwargs)

                # Commit subscription usage on success
                subscription_usage_plugin = get_plugin("subscription_usage")
                if subscription_usage_plugin:
                    try:
                        service = subscription_usage_plugin["service_class"]()
                        service.commit_subscription_usage(
                            org_id=org_id,
                            date_key=datetime.now().date(),
                            file_execution_id=file_execution_id,
                        )
                        logger.info(
                            f"Committed subscription usage for file_execution_id {file_execution_id}"
                        )
                    except Exception as commit_error:
                        logger.error(
                            f"Error committing subscription usage for "
                            f"file_execution_id {file_execution_id}: {commit_error}"
                        )

                return result

            except Exception:
                # Discard subscription usage on failure
                subscription_usage_plugin = get_plugin("subscription_usage")
                if subscription_usage_plugin:
                    try:
                        service = subscription_usage_plugin["service_class"]()
                        service.discard_subscription_usage(
                            org_id=org_id,
                            date_key=datetime.now().date(),
                            file_execution_id=file_execution_id,
                        )
                        logger.info(
                            f"Discarded subscription usage for file_execution_id {file_execution_id}"
                        )
                    except Exception as discard_error:
                        logger.error(
                            f"Error discarding subscription usage for "
                            f"file_execution_id {file_execution_id}: {discard_error}"
                        )

                # Re-raise original exception
                raise

        return wrapper

    return decorator
