import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from unstract.core.network.enums import HTTPMethod


def get_retry_session(
    retry_count: int = 5,
    backoff_factor: int = 3,
    status_forcelist: list[int] | None = None,
    allowed_methods: list[str] | None = None,
    raise_on_status: bool = False,
    enable_http: bool = True,
    enable_https: bool = True,
) -> requests.Session:
    """Get retry adapter for requests.

    This function creates a requests session with a retry strategy.

    Args:
        retry_count (int, optional): Number of retries. Defaults to 5.
        backoff_factor (int, optional): Base delay for exponential backoff.
            The wait time before retry attempt N is:
                backoff_factor * (2^(N-1)) seconds

            Example (backoff_factor=3):
                Attempt 1: 3 * 1 = 3s
                Attempt 2: 3 * 2 = 6s
                Attempt 3: 3 * 4 = 12s
            Defaults to 3.
        status_forcelist (list, optional): List of status codes to retry. Defaults to None.
        allowed_methods (list, optional): List of allowed methods. Defaults to None.
        raise_on_status (bool, optional): Whether to raise on status. Defaults to False.
        enable_http (bool, optional): Whether to enable http. Defaults to True.
        enable_https (bool, optional): Whether to enable https. Defaults to True.

    Returns:
        requests.Session: HTTP session with retry strategy.

    Examples:
        >>> session = get_retry_session(
            retry_count=5,
            backoff_factor=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=[HTTPMethod.GET.value, HTTPMethod.POST.value],
            raise_on_status=False,
            enable_http=True,
            enable_https=True,
        )
        >>> response = session.get("https://example.com")
    """
    status_forcelist = status_forcelist or [429, 500, 502, 503, 504]
    allowed_methods = allowed_methods or [HTTPMethod.GET.value, HTTPMethod.POST.value]
    retry_strategy = Retry(
        total=retry_count,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
        raise_on_status=raise_on_status,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    if enable_http:
        session.mount("http://", adapter)
    if enable_https:
        session.mount("https://", adapter)
    return session
