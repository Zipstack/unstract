"""Basic Controller."""

import logging
from io import BytesIO
from typing import Any

import requests
from flask import Blueprint, request, send_file

from app.authentication_middleware import (
    AuthenticationMiddleware,
    authentication_middleware,
)
from app.models import X2TextAudit
from app.unstructured_url import RedirectRefused, refusal_message
from app.unstructured_url import post as post_to_unstructured
from app.util import X2TextUtil
from unstract.core.network.ssrf import safe_host

basic = Blueprint("basic", __name__)
# Configure the logging format and level
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

UNSTRUCTURED_URL = "unstructured-url"
UNSTRUCTURED_API_KEY = "unstructured-api-key"

TIMED_OUT = "Timed out waiting for the Unstructured API"
UNREACHABLE = "Unable to reach the Unstructured API"


def _error(message: str, status: int = 400) -> tuple[dict[str, str], int]:
    """An error response whose reason reaches the user.

    ``detail`` is the key sdk1 reads an error message from; ``message`` matches
    this service's other responses.
    """
    return {"message": message, "detail": message}, status


def _status_detail(status: int) -> str:
    """A user-facing reason for an upstream status, without its body."""
    hint = {
        401: "; check the API key, or whether this server needs one",
        403: "; check the API key, or whether this server needs one",
        404: "; check the URL path",
    }.get(status, "")
    return f"Unstructured API returned HTTP {status}{hint}"


# What a wrong or unreachable adapter URL raises: the tenant's to fix, so a
# warning. SSL and proxy errors subclass ConnectionError but point at this
# service's own egress, so they stay errors along with every other transport
# fault (a reset mid-body, too many redirects, ...).
_ADAPTER_URL_ERRORS = (
    requests.ConnectionError,
    requests.exceptions.InvalidURL,
    requests.exceptions.MissingSchema,
    requests.exceptions.InvalidSchema,
)
_EGRESS_ERRORS = (requests.exceptions.SSLError, requests.exceptions.ProxyError)


def _log_transport_error(what: str, error: requests.RequestException, url: str) -> None:
    """Log a transport failure by type and host only.

    Neither ``str(error)`` nor the traceback: both carry the full URL, query
    string (and any key in it) included.
    """
    expected = isinstance(error, _ADAPTER_URL_ERRORS) and not isinstance(
        error, _EGRESS_ERRORS
    )
    logging.log(
        logging.WARNING if expected else logging.ERROR,
        "%s could not reach the Unstructured API: %s (host=%s)",
        what,
        type(error).__name__,
        safe_host(url),
    )


def _redirect_refused(error: RedirectRefused, url: str) -> tuple[dict[str, str], int]:
    logging.warning("Redirect refused: %s (host=%s)", error, safe_host(url))
    # A fixed string chosen by the exception's class, never its text.
    return _error(type(error).user_message)


@basic.route("/health", methods=["GET"])
def health() -> str:
    logging.info("Checking health from : %s", request.remote_addr)
    return "OK"


@basic.route("/test-connection", methods=["POST"])
@authentication_middleware
def test_connection() -> Any:
    logging.info("Received a test connection request from %s", request.remote_addr)
    form_data = dict(request.form)
    unstructured_api_key = X2TextUtil.get_value_for_key(UNSTRUCTURED_API_KEY, form_data)
    url = X2TextUtil.get_value_for_key(UNSTRUCTURED_URL, form_data)
    if not url:
        return {"message": "Missing or empty url in form data"}, 400
    if refusal := refusal_message(url):
        return _error(refusal)

    headers = {
        "accept": "application/json",
        "unstructured-api-key": unstructured_api_key,
    }

    try:
        response = post_to_unstructured(
            url, headers=headers, data=None, files=lambda: {"files": ("test")}
        )

        if response.status_code == 400:
            """Response is 400 as we are not sending a file to test connection.

            But it has passed credential check and url check
            """

            return {"message": "Test connection sucessful"}, 200
        # The upstream body stays under ``message``, which sdk1 does not show:
        # where private destinations are allowed it may be an internal
        # service's error page.
        return {
            "message": response.text,
            "detail": _status_detail(response.status_code),
        }, response.status_code
    except RedirectRefused as e:
        return _redirect_refused(e, url)
    except requests.Timeout:
        logging.error("Test connection timed out waiting for the Unstructured API")
        return _error(TIMED_OUT, 504)
    except requests.RequestException as e:
        _log_transport_error("Test connection", e, url)
        return _error(UNREACHABLE)
    except Exception:
        logging.exception("Test connection failed (host=%s)", safe_host(url))
        return _error("Test connection failed")


@basic.route("/process", methods=["POST"])
@authentication_middleware
def process() -> Any:
    logging.info("Received a doc processing request from %s", request.remote_addr)
    form_data = dict(request.form)
    url = X2TextUtil.get_value_for_key(UNSTRUCTURED_URL, form_data)
    if not url:
        return {"message": "Missing or empty url in form data"}, 400
    if refusal := refusal_message(url):
        return _error(refusal)
    if "file" not in request.files:
        return {"message": "No file part"}, 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return {"message": "No selected file"}, 400

    file_size_in_kb = int(request.headers["Content-Length"]) / 1024

    bearer_token = AuthenticationMiddleware.get_token_from_auth_header(request)
    _, org_id = AuthenticationMiddleware.get_organization_from_bearer_token(bearer_token)

    x2_text_audit: X2TextAudit = X2TextAudit.create(
        org_id=org_id,
        file_name=uploaded_file.filename,
        file_type=uploaded_file.mimetype,
        file_size_in_kb=round(file_size_in_kb, 2),
    )

    def files() -> dict[str, Any]:
        # Rewound for each send: a 307/308 replays the upload.
        uploaded_file.stream.seek(0)
        return {
            "files": (
                uploaded_file.filename,
                uploaded_file.stream,
                uploaded_file.content_type,
            )
        }

    unstructured_api_key = X2TextUtil.get_value_for_key(UNSTRUCTURED_API_KEY, form_data)
    headers = {
        "accept": "application/json",
        "unstructured-api-key": unstructured_api_key,
    }
    payload = form_data

    try:
        response = post_to_unstructured(url, headers=headers, data=payload, files=files)
    except RedirectRefused as e:
        x2_text_audit.status = "Failed"
        x2_text_audit.save()
        return _redirect_refused(e, url)
    except requests.Timeout:
        x2_text_audit.status = "Failed"
        x2_text_audit.save()
        logging.error("Text extraction timed out waiting for the Unstructured API")
        return _error(TIMED_OUT, 504)
    except requests.RequestException as e:
        x2_text_audit.status = "Failed"
        x2_text_audit.save()
        _log_transport_error("Text extraction", e, url)
        return _error(UNREACHABLE, 502)
    if response.ok:
        json_response = response.json()
        response_text = X2TextUtil.get_text_content(json_response)
        file_stream = BytesIO(response_text.encode("utf-8"))
        x2_text_audit.status = "Success"
        x2_text_audit.save()
        return send_file(file_stream, download_name="infile.txt", as_attachment=True)
    x2_text_audit.status = "Failed"
    x2_text_audit.save()
    return_val = X2TextUtil.read_response(response=response)
    logging.error("Text extraction failed: [%s] %s", response.status_code, return_val)
    return return_val, response.status_code
