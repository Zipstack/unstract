import json
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


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
    # Return original data if webhook not enabled or URL not provided
    if not webhook_enabled or not webhook_url:
        return parsed_data, highlight_data

    payload = {"structured_output": parsed_data}
    if highlight_data is not None:
        payload["highlight_data"] = highlight_data

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            try:
                response_data = response.json()
                if "structured_output" in response_data:
                    updated_parsed_data = response_data["structured_output"]
                    # Ensure we only accept dict or list payloads
                    if not isinstance(updated_parsed_data, (dict, list)):
                        logger.warning(
                            "Ignoring postprocessing due to invalid structured_output type"
                        )
                        return parsed_data, highlight_data
                    updated_highlight_data = response_data.get(
                        "highlight_data", highlight_data
                    )
                    # Validate highlight_data type if it was updated from webhook
                    if (
                        updated_highlight_data is not None
                        and updated_highlight_data != highlight_data
                        and not isinstance(updated_highlight_data, list)
                    ):
                        logger.warning(
                            "Ignoring webhook highlight_data due to invalid type (expected list)"
                        )
                        updated_highlight_data = highlight_data
                    return updated_parsed_data, updated_highlight_data
                else:
                    logger.warning("Response missing 'structured_output' key")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Invalid JSON response from postprocessing server: {e}")
        else:
            logger.warning(
                f"Postprocessing server returned status code: {response.status_code}"
            )

    except requests.exceptions.Timeout:
        logger.warning(f"Postprocessing server request timed out after {timeout}s")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Postprocessing server request failed: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error during postprocessing: {e}")

    return parsed_data, highlight_data
