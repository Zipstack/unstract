import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _validate_structured_output(data: Any) -> bool:
    """Validate that structured output is a dict or list."""
    return isinstance(data, (dict, list))


def _validate_highlight_data(updated_data: Any, original_data: Any) -> Any:
    """Validate highlight data and return appropriate value."""
    if (
        updated_data is not None
        and updated_data != original_data
        and not isinstance(updated_data, list)
    ):
        logger.warning(
            "Ignoring webhook highlight_data due to invalid type (expected list)"
        )
        return original_data
    return updated_data


def _process_successful_response(
    response_data: dict, parsed_data: dict, highlight_data: list | None
) -> tuple[dict[str, Any], list | None]:
    """Process successful webhook response."""
    if "structured_output" not in response_data:
        logger.warning("Response missing 'structured_output' key")
        return parsed_data, highlight_data

    updated_parsed_data = response_data["structured_output"]

    if not _validate_structured_output(updated_parsed_data):
        logger.warning("Ignoring postprocessing due to invalid structured_output type")
        return parsed_data, highlight_data

    updated_highlight_data = response_data.get("highlight_data", highlight_data)
    updated_highlight_data = _validate_highlight_data(
        updated_highlight_data, highlight_data
    )

    return updated_parsed_data, updated_highlight_data


def _make_webhook_request(
    webhook_url: str, payload: dict, timeout: float
) -> tuple[dict[str, Any], list | None] | None:
    """Make webhook request and return processed response or None on failure."""
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
            allow_redirects=False,  # Prevent redirect-based SSRF
        )

        if response.status_code != 200:
            logger.warning(
                f"Postprocessing server returned status code: {response.status_code}"
            )
            return None

        return response.json()

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON response from postprocessing server: {e}")
    except requests.exceptions.Timeout:
        logger.warning(f"Postprocessing server request timed out after {timeout}s")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Postprocessing server request failed: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error during postprocessing: {e}")

    return None


def postprocess_data(
    parsed_data: dict[str, Any],
    webhook_enabled: bool = False,
    webhook_url: str | None = None,
    timeout: float = 2.0,
    highlight_data: list | None = None,
) -> tuple[dict[str, Any], list | None]:
    """Post-process parsed data by sending it to an external server.

    Args:
        parsed_data: The parsed data to be post-processed
        webhook_enabled: Whether webhook postprocessing is enabled
        webhook_url: URL endpoint for the webhook
        timeout: Request timeout in seconds (default: 2.0)
        highlight_data: Highlight data from metadata to send to webhook

    Returns:
        tuple: (postprocessed_data, updated_highlight_data) if successful, otherwise (original_parsed_data, original_highlight_data)
    """
    if not webhook_enabled or not webhook_url:
        return parsed_data, highlight_data

    payload = {"structured_output": parsed_data}
    if highlight_data is not None:
        payload["highlight_data"] = highlight_data

    response_data = _make_webhook_request(webhook_url, payload, timeout)
    if response_data is None:
        return parsed_data, highlight_data

    return _process_successful_response(response_data, parsed_data, highlight_data)
