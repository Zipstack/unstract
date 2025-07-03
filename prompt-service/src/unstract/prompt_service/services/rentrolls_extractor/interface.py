import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class RentRollExtractor:
    """Main class for rent roll extraction."""

    def __init__(self):
        """Initialize the rent roll extractor."""
        logger.info("Initialized RentRollExtractor")
        pass

    async def process(
        self,
        extractor_settings: dict[str, Any],
        extracted_data: str,
        llm_config: dict[str, Any],
        schema: str,
    ) -> dict[str, Any]:
        """Process the extraction with the given settings.

        Args:
            extractor_settings: Dictionary containing extraction settings.
            extracted_data: Extracted data from the document.
            llm_config: Dictionary containing LLM configuration.
            schema: Schema for the extraction.

        Returns:
            Dict containing the extraction results.
        """
        logger.info("Starting rent roll extraction process")
        try:
            # Load environment variables for rent roll service
            rentroll_host = os.environ.get("RENTROLL_SERVICE_HOST", "http://localhost")
            rentroll_port = os.environ.get("RENTROLL_SERVICE_PORT", "5003")
            rentroll_url = f"{rentroll_host}:{rentroll_port}/api/extract-rentrolls"

            # Prepare the request payload
            payload = {
                "text": extracted_data,
                "settings": extractor_settings,
                "llm_config": llm_config,
                "schema": schema,
            }

            # Make HTTP call to rent roll service
            timeout = aiohttp.ClientTimeout(total=1800) 
            logger.info(f"Calling rent roll service at: {rentroll_url}")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(rentroll_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(
                            "Successfully received response from rent roll service"
                        )
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Rent roll service returned status {response.status}: {error_text}"
                        )
                        raise Exception(
                            f"Rent roll service error: {response.status} - {error_text}"
                        )
        except Exception as e:
            logger.error(f"Error in rent roll extraction: {str(e)}", exc_info=True)
            raise
