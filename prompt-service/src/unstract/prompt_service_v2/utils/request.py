import logging
from enum import Enum
from typing import Any, Optional

import requests as pyrequests
from requests.exceptions import RequestException
from unstract.prompt_service_v2.exceptions import (
    APIError,
    BadRequest,
    MissingFieldError,
)

logger = logging.getLogger(__name__)


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"
    PUT = "PUT"
    PATCH = "PATCH"


def make_http_request(
    verb: HTTPMethod,
    url: str,
    data: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> str:
    """Generic helper function to help make a HTTP request."""
    try:
        if verb == HTTPMethod.GET:
            response = pyrequests.get(url, params=params, headers=headers)
        elif verb == HTTPMethod.POST:
            response = pyrequests.post(url, json=data, params=params, headers=headers)
        elif verb == HTTPMethod.DELETE:
            response = pyrequests.delete(url, params=params, headers=headers)
        else:
            raise ValueError("Invalid HTTP verb. Supported verbs: GET, POST, DELETE")

        response.raise_for_status()
        return_val: str = (
            response.json()
            if response.headers.get("content-type") == "application/json"
            else response.text
        )
        return return_val
    except RequestException as e:
        logger.error(f"HTTP request error: {e}")
        raise APIError(f"Error occured while invoking POST API Variable : {str(e)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise e


def validate_request_payload(payload):
    if not payload:
        raise BadRequest()

    # Validate required fields
    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise MissingFieldError(missing_fields)
