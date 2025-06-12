import logging

import requests

from unstract.core.network.enums import HTTPMethod

logger = logging.getLogger(__name__)


class HttpClient:
    """Lightweight HTTP client wrapper around `requests.Session`, supporting retries and timeout.

    Allows making API requests with configurable base URL and default timeout.
    """

    def __init__(
        self, session: requests.Session, base_url: str, timeout: int | None = None
    ):
        """Initialize HttpClient with a session, base URL, and optional timeout.

        Args:
            session (requests.Session): Session object for making requests.
            base_url (str): Base URL for the API.
            timeout (int | None): Optional timeout for requests.
        """
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: HTTPMethod,
        endpoint: str,
        timeout: int | None = None,
        raise_on_status: bool = True,
        **kwargs,
    ):
        """Make api request using session with retry strategy.

        Args:
            method (HTTPMethod): HTTP method
            endpoint (str): API endpoint
            timeout (int | None): Override timeout for this request. Falls back to class-level timeout.
            raise_on_status (bool): If True, raises HTTPError on non-2xx responses.
            **kwargs: Additional keyword arguments to pass to requests.request

        Returns:
            requests.Response: Response object
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        timeout = timeout or self.timeout
        try:
            response = self.session.request(
                method=method.value, url=url, timeout=timeout, **kwargs
            )
            if raise_on_status:
                response.raise_for_status()  # Raise HTTP errors
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"{method} {url} failed :{e}")
            raise

    __call__ = request
