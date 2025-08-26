"""Base HTTP Client for Internal API Communication

This module provides the foundational HTTP client functionality extracted from
the monolithic InternalAPIClient. It handles session management, retry logic,
authentication, and common request/response patterns.

All specialized clients inherit from BaseAPIClient to get consistent HTTP behavior.
"""

import json
import logging
import os
import time
import uuid
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import WorkerConfig
from ..data_models import APIResponse
from ..enums import HTTPMethod
from ..logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)

# HTTP Content Type Constants
APPLICATION_JSON = "application/json"


class InternalAPIClientError(Exception):
    """Base exception for API client errors."""

    pass


class AuthenticationError(InternalAPIClientError):
    """Raised when API authentication fails."""

    pass


class APIRequestError(InternalAPIClientError):
    """Raised when API request fails."""

    pass


class BaseAPIClient:
    """Base HTTP client for communicating with Django backend internal APIs.

    Features:
    - Bearer token authentication
    - Automatic retries with exponential backoff
    - Request/response logging
    - Organization context support
    - Circuit breaker pattern
    - Connection pooling
    - Request batching support
    """

    # Internal API URL patterns - can be overridden via environment variables
    # Standardized to use v1/ prefix consistently, with v2/ for newer optimized endpoints
    API_ENDPOINTS = {
        "health": os.getenv("INTERNAL_API_HEALTH_PREFIX", "v1/health/"),
        "workflow_execution": os.getenv(
            "INTERNAL_API_WORKFLOW_PREFIX", "v1/workflow-execution/"
        ),
        "organization": os.getenv("INTERNAL_API_ORGANIZATION_PREFIX", "v1/organization/"),
        "execution": os.getenv("INTERNAL_API_EXECUTION_PREFIX", "v1/execution/"),
        "tool_execution": os.getenv(
            "INTERNAL_API_TOOL_EXECUTION_PREFIX", "v1/tool-execution/"
        ),
        "file_execution": os.getenv(
            "INTERNAL_API_FILE_EXECUTION_PREFIX", "v1/file-execution/"
        ),
        "file_history": os.getenv("INTERNAL_API_FILE_HISTORY_PREFIX", "v1/file-history/"),
        "webhook": os.getenv("INTERNAL_API_WEBHOOK_PREFIX", "v1/webhook/"),
        "workflow_manager": os.getenv(
            "INTERNAL_API_WORKFLOW_MANAGER_PREFIX", "v1/workflow-manager/"
        ),
        "platform_settings": os.getenv(
            "INTERNAL_API_PLATFORM_SETTINGS_PREFIX", "v1/platform-settings/"
        ),
        # API deployment endpoints for optimized type-aware operations
        "api_deployments": os.getenv(
            "INTERNAL_API_DEPLOYMENTS_PREFIX", "v1/api-deployments/"
        ),
    }

    def __init__(self, config: WorkerConfig | None = None):
        """Initialize base API client.

        Args:
            config: Worker configuration. If None, uses default config.
        """
        self.config = config or WorkerConfig()
        self.base_url = self.config.internal_api_base_url
        self.api_key = self.config.internal_api_key
        self.organization_id = self.config.organization_id

        # Initialize requests session with retry strategy
        self.session = requests.Session()
        self._setup_session()

        logger.info(f"Initialized BaseAPIClient for {self.base_url}")
        logger.debug(f"API endpoint configuration: {self.get_endpoint_config()}")

    def get_endpoint_config(self) -> dict[str, str]:
        """Get current API endpoint configuration for debugging."""
        return dict(self.API_ENDPOINTS)

    def _build_url(self, endpoint_key: str, path: str = "") -> str:
        """Build consistent API URL using endpoint patterns.

        Args:
            endpoint_key: Key from API_ENDPOINTS dict
            path: Additional path to append

        Returns:
            Complete endpoint path
        """
        base_path = self.API_ENDPOINTS.get(endpoint_key, endpoint_key)
        if path:
            return f"{base_path.rstrip('/')}/{path.lstrip('/')}"
        # Preserve trailing slashes in base_path to avoid 301 redirects
        return base_path

    def _setup_session(self):
        """Configure session with retry strategy, timeouts, and connection pooling."""
        # Enhanced retry strategy with enum-based status codes
        retry_status_codes = [429, 500, 502, 503, 504]
        allowed_http_methods = [method.value for method in HTTPMethod]

        retry_strategy = Retry(
            total=self.config.api_retry_attempts,
            backoff_factor=self.config.api_retry_backoff_factor,
            status_forcelist=retry_status_codes,
            allowed_methods=allowed_http_methods,
            respect_retry_after_header=True,
        )

        # HTTP adapter with connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,  # Maximum number of connections per pool
            pool_block=False,  # Don't block when pool is full
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Default headers
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": APPLICATION_JSON,
                "User-Agent": f"UnstractWorker/{self.config.worker_version}",
                "Accept": APPLICATION_JSON,
                "Connection": "keep-alive",
            }
        )

        # Organization context header
        if self.organization_id:
            self.session.headers["X-Organization-ID"] = self.organization_id

    def _serialize_data(self, data: Any) -> Any:
        """Recursively serialize data to JSON-compatible format.
        Handles UUID objects, datetime objects, and other complex types.
        """
        import datetime

        if isinstance(data, uuid.UUID):
            return str(data)
        elif isinstance(data, (datetime.datetime, datetime.date)):
            return data.isoformat()
        elif isinstance(data, datetime.time):
            return data.isoformat()
        elif isinstance(data, dict):
            return {key: self._serialize_data(value) for key, value in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._serialize_data(item) for item in data]
        elif isinstance(data, set):
            return [self._serialize_data(item) for item in data]
        else:
            return data

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Enhanced HTTP request with robust error handling and retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (relative to base URL)
            data: Request payload for POST/PUT/PATCH
            params: Query parameters
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Exponential backoff factor
            organization_id: Optional organization ID override

        Returns:
            Response data as dictionary

        Raises:
            AuthenticationError: If authentication fails
            APIRequestError: If request fails after all retries
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        timeout = timeout or self.config.api_timeout

        last_exception = None
        # HTTP status codes that should trigger retries
        retry_statuses = {500, 502, 503, 504}  # Server errors to retry
        auth_error_status = 401
        client_error_range = range(400, 500)
        timeout_statuses = {408, 429}

        for attempt in range(max_retries + 1):
            try:
                is_retry = attempt > 0
                log_level = (
                    logging.WARNING if is_retry else logging.INFO
                )  # Changed to INFO for debugging
                logger.log(
                    log_level,
                    f"DEBUG: Making {method} request to {url} (attempt {attempt + 1}/{max_retries + 1})",
                )

                # Prepare request kwargs
                kwargs = {"timeout": timeout, "params": params, "allow_redirects": True}

                # Handle dynamic organization context
                headers = {}
                current_org_id = organization_id or self.organization_id
                if current_org_id:
                    headers["X-Organization-ID"] = current_org_id
                    if attempt == 0:  # Only log on first attempt
                        logger.info(
                            f"DEBUG: Including organization header: X-Organization-ID={current_org_id}"
                        )
                else:
                    if attempt == 0:  # Only log on first attempt
                        logger.warning(
                            f"DEBUG: NO organization header - current_org_id={current_org_id}, "
                            f"organization_id param={organization_id}, self.organization_id={self.organization_id}"
                        )

                if headers:
                    kwargs["headers"] = headers
                    if attempt == 0:  # Only log on first attempt
                        logger.info(
                            f"DEBUG: Request headers being sent: {list(headers.keys())}"
                        )
                else:
                    if attempt == 0:  # Only log on first attempt
                        logger.warning("DEBUG: NO custom headers being sent")

                # Serialize request data
                if data is not None:
                    try:
                        kwargs["json"] = self._serialize_data(data)
                    except Exception as e:
                        logger.error(f"Failed to serialize request data: {e}")
                        raise APIRequestError(f"Data serialization failed: {str(e)}")

                # Make request with session (includes connection pooling)
                response = self.session.request(method, url, **kwargs)

                # Enhanced response logging
                logger.info(
                    f"DEBUG: Response: {response.status_code} {response.reason} "
                    f"(Content-Length: {response.headers.get('Content-Length', 'unknown')}) "
                    f"URL: {url}"
                )

                # Handle authentication errors (don't retry)
                if response.status_code == auth_error_status:
                    error_msg = "Authentication failed with internal API"
                    response_text = self._safe_get_response_text(response)
                    logger.error(f"{error_msg}: {response_text}")
                    raise AuthenticationError(f"{error_msg}: {response_text}")

                # Handle client errors (don't retry most 4xx)
                if (
                    response.status_code in client_error_range
                    and response.status_code not in timeout_statuses
                ):
                    error_msg = f"Client error: {response.status_code} {response.reason}"
                    response_text = self._safe_get_response_text(response)
                    logger.error(f"{error_msg}: {response_text}")
                    raise APIRequestError(f"{error_msg}: {response_text}")

                # Handle server errors (retry these)
                if response.status_code in retry_statuses:
                    error_msg = f"Server error: {response.status_code} {response.reason}"
                    response_text = self._safe_get_response_text(response)

                    if attempt < max_retries:
                        sleep_time = backoff_factor * (2**attempt)
                        logger.warning(
                            f"{error_msg} - retrying in {sleep_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.error(
                            f"{error_msg} - max retries exceeded: {response_text}"
                        )
                        raise APIRequestError(f"{error_msg}: {response_text}")

                # Handle rate limiting (429)
                rate_limit_status = 429
                if response.status_code == rate_limit_status:
                    retry_after = int(
                        response.headers.get("Retry-After", backoff_factor * (2**attempt))
                    )
                    if attempt < max_retries:
                        logger.warning(
                            f"Rate limited - retrying in {retry_after}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(retry_after)
                        continue
                    else:
                        raise APIRequestError(
                            f"Rate limited after {max_retries + 1} attempts"
                        )

                # Success case
                if response.ok:
                    return self._parse_response(response, endpoint)

                # Other errors
                error_msg = f"Request failed: {response.status_code} {response.reason}"
                response_text = self._safe_get_response_text(response)
                logger.error(f"{error_msg}: {response_text}")
                raise APIRequestError(f"{error_msg}: {response_text}")

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as e:
                last_exception = e
                error_type = (
                    "timeout"
                    if isinstance(e, requests.exceptions.Timeout)
                    else "connection"
                )

                if attempt < max_retries:
                    sleep_time = backoff_factor * (2**attempt)
                    logger.warning(
                        f"Request {error_type} error - retrying in {sleep_time:.1f}s (attempt {attempt + 1}/{max_retries + 1}): {str(e)}"
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    logger.error(
                        f"Request {error_type} error after {max_retries + 1} attempts: {str(e)}"
                    )
                    raise APIRequestError(f"Request {error_type} error: {str(e)}")

            except requests.exceptions.RequestException as e:
                last_exception = e
                error_msg = f"Request exception: {str(e)}"
                logger.error(error_msg)
                raise APIRequestError(error_msg)

            except (AuthenticationError, APIRequestError):
                # Re-raise these without retrying
                raise

            except Exception as e:
                last_exception = e
                error_msg = f"Unexpected error during API request: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise APIRequestError(error_msg)

        # This shouldn't be reached, but just in case
        error_msg = f"Request failed after {max_retries + 1} attempts"
        if last_exception:
            error_msg += f": {str(last_exception)}"
        raise APIRequestError(error_msg)

    def _safe_get_response_text(
        self, response: requests.Response, max_length: int = 500
    ) -> str:
        """Safely get response text with error handling and length limiting."""
        try:
            text = response.text
            if len(text) > max_length:
                return f"{text[:max_length]}... (truncated)"
            return text
        except Exception as e:
            return f"<Could not read response text: {str(e)}>"

    def _parse_response(
        self, response: requests.Response, endpoint: str
    ) -> dict[str, Any]:
        """Enhanced response parsing with better error handling."""
        try:
            # Check content type
            content_type = response.headers.get("Content-Type", "").lower()

            if APPLICATION_JSON in content_type:
                json_data = response.json()
                logger.debug(f"Successfully parsed JSON response from {endpoint}")
                return json_data
            elif response.text.strip():
                # Try to parse as JSON anyway (some APIs don't set correct Content-Type)
                try:
                    json_data = response.json()
                    logger.debug(
                        f"Successfully parsed JSON response (incorrect Content-Type) from {endpoint}"
                    )
                    return json_data
                except json.JSONDecodeError:
                    # Return raw text
                    logger.debug(f"Returning raw text response from {endpoint}")
                    return {"raw_response": response.text}
            else:
                # Empty response
                logger.debug(f"Empty response from {endpoint}")
                return {}

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response from {endpoint}: {str(e)}")
            return {"raw_response": response.text, "parse_error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error parsing response from {endpoint}: {str(e)}")
            return {"error": f"Response parsing failed: {str(e)}"}

    def _batch_request(self, requests_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch multiple requests for improved performance.

        Args:
            requests_data: List of request dictionaries with 'method', 'endpoint', and optional 'data', 'params'

        Returns:
            List of response dictionaries
        """
        results = []

        for request_data in requests_data:
            try:
                method = request_data["method"]
                endpoint = request_data["endpoint"]
                data = request_data.get("data")
                params = request_data.get("params")

                result = self._make_request(method, endpoint, data=data, params=params)
                results.append({"success": True, "data": result})

            except Exception as e:
                logger.error(f"Batch request failed for {request_data}: {str(e)}")
                results.append({"success": False, "error": str(e)})

        return results

    # HTTP method helpers using enums
    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        """Make GET request."""
        return self._make_request(
            HTTPMethod.GET.value, endpoint, params=params, organization_id=organization_id
        )

    def post(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make POST request."""
        return self._make_request(
            HTTPMethod.POST.value, endpoint, data=data, organization_id=organization_id
        )

    def put(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make PUT request."""
        return self._make_request(
            HTTPMethod.PUT.value, endpoint, data=data, organization_id=organization_id
        )

    def patch(
        self, endpoint: str, data: dict[str, Any], organization_id: str | None = None
    ) -> dict[str, Any]:
        """Make PATCH request."""
        return self._make_request(
            HTTPMethod.PATCH.value, endpoint, data=data, organization_id=organization_id
        )

    def delete(self, endpoint: str, organization_id: str | None = None) -> dict[str, Any]:
        """Make DELETE request."""
        return self._make_request(
            HTTPMethod.DELETE.value, endpoint, organization_id=organization_id
        )

    # Organization context management
    def set_organization_context(self, org_id: str):
        """Set organization context for subsequent requests."""
        logger.info(
            f"DEBUG: set_organization_context called with org_id='{org_id}' (type: {type(org_id).__name__})"
        )

        if org_id is None or str(org_id).lower() == "none":
            logger.error(
                f"DEBUG: Attempted to set organization context with invalid value: '{org_id}' - skipping header"
            )
            self.organization_id = None
            # Don't set the header if org_id is None
            if "X-Organization-ID" in self.session.headers:
                del self.session.headers["X-Organization-ID"]
                logger.info("DEBUG: Removed X-Organization-ID header from session")
            return

        self.organization_id = org_id
        self.session.headers["X-Organization-ID"] = org_id
        logger.info(
            f"DEBUG: Set organization context to '{org_id}' - header added to session"
        )
        logger.info(
            f"DEBUG: Session headers now include: {list(self.session.headers.keys())}"
        )

    def clear_organization_context(self):
        """Clear organization context."""
        self.organization_id = None
        if "X-Organization-ID" in self.session.headers:
            del self.session.headers["X-Organization-ID"]
        logger.debug("Cleared organization context")

    # Health check
    def health_check(self) -> APIResponse:
        """Check API health status."""
        try:
            response = self.get(self._build_url("health"))
            return APIResponse(
                success=response.get("status") == "healthy",
                data=response,
                status_code=200,
            )
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    # Session management
    def close(self):
        """Close the HTTP session."""
        self.session.close()
        logger.debug("Closed API client session")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
