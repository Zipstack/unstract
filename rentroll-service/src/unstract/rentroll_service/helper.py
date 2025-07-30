import logging
import os
import shutil
from pathlib import Path
from typing import Any

from autogen_ext.models.anthropic import AnthropicChatCompletionClient
from autogen_ext.models.openai import (
    AzureOpenAIChatCompletionClient,
    OpenAIChatCompletionClient,
)

from runner import RentRollExtractorRunner

logger = logging.getLogger(__name__)
DEBUG = os.getenv("DEBUG", "true").lower() == "true"


def get_llm_client(
    llm_config: dict[str, Any],
) -> (
    OpenAIChatCompletionClient
    | AzureOpenAIChatCompletionClient
    | AnthropicChatCompletionClient
):
    """Initialize and return an LLM client."""
    try:
        llm_client = None
        if llm_config.get("adapter_id") == "azureopenai":
            llm_client = AzureOpenAIChatCompletionClient(
                model=llm_config.get("model"),
                azure_endpoint=llm_config.get("api_base"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                api_version=llm_config.get("api_version"),
                api_key=llm_config.get("api_key"),
                azure_deployment=llm_config.get("deployment"),
                timeout=llm_config.get("timeout", 900),
            )
        if llm_config.get("adapter_id") == "openai":
            llm_client = OpenAIChatCompletionClient(
                model=llm_config.get("model"),
                api_key=llm_config.get("api_key"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                request_timeout=llm_config.get("request_timeout", 60),
                base_url=llm_config.get("api_base"),
                max_retries=llm_config.get("max_retries", 3),
                timeout=llm_config.get("timeout", 900),
            )
        if llm_config.get("adapter_id") == "anthropic":
            llm_client = AnthropicChatCompletionClient(
                model=llm_config.get("model"),
                api_key=llm_config.get("api_key"),
                temperature=llm_config.get("temperature", 0.1),
                max_tokens=llm_config.get("max_tokens", 4096),
                base_url=llm_config.get("api_base"),
            )
        return llm_client
    except Exception as e:
        error_msg = f"Failed to initialize LLM client: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


def _setup_temp_dir() -> str:
    """Create a temporary directory that will be cleaned up automatically."""
    current_dir = Path(__file__).parent
    temp_dir_path = current_dir / f"temp_rentroll_{os.getpid()}"
    os.makedirs(temp_dir_path, exist_ok=True)
    logger.info(f"Created temporary directory at: {temp_dir_path}")
    return str(temp_dir_path)


def _cleanup_temp_dir(temp_dir: str) -> None:
    """Clean up the temporary directory if it exists."""
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up {temp_dir}: {str(e)}")


async def extract_rent_roll(
    schema: dict[str, Any],
    extracted_data: str,
    llm_config: dict[str, Any],
) -> dict[str, Any]:
    """Extract rent roll data using the specified settings."""
    temp_dir = None
    try:
        temp_dir = _setup_temp_dir()
        # AutoGen OpenAI Chat completion client
        llm_client = get_llm_client(llm_config)
        runner = RentRollExtractorRunner(llm_client, output_dir=temp_dir)

        input_file = None
        if extracted_data:
            # Define the path for the new file
            data_file_path = Path(temp_dir) / "extracted.txt"

            # Write the data to the file
            data_file_path.write_text(extracted_data, encoding="utf-8")

            # Update the input_file variable to point to our new data file
            input_file = str(data_file_path)

        if not input_file:
            raise Exception("No input data provided.")

        result = await runner.run(
            input_file=input_file,
            schema=schema,
        )

        return result

    except Exception as e:
        error_msg = f"Error during rent roll extraction: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e
    finally:
        if not DEBUG and temp_dir:
            _cleanup_temp_dir(temp_dir)
