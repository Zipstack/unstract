import logging
from typing import Optional

from backend.exceptions import LLMHelperError
from unstract.core.llm_helper.enums import LLMResult, PromptContext
from unstract.core.llm_helper.llm_helper import LLMHelper
from unstract.core.llm_helper.models import LLMResponse

logger = logging.getLogger(__name__)


class CronGenerator:
    """Uses LLM to generate a cron string for a user input of frequency."""

    @staticmethod
    def generate_cron(frequency: str, cache_key_prefix: Optional[str] = None) -> str:
        """Generates cron for a user provided description of frequency.

        Uses LLM to prefix the user input with a prompt template and generate cron

        Args:
            frequency (str): User provided input
            cache_key (Optional[str], optional): Key to cache against. Defaults to None.

        Returns:
            str: Generated cron string
        """
        cron_response: LLMResponse
        logging.info(f"Generating cron for '{frequency}'")
        use_cache = True
        if cache_key_prefix is None:
            use_cache = False
        cron_llm = LLMHelper(
            cache_key_prefix=cache_key_prefix,
            prompt_context=PromptContext.GENERATE_CRON_STRING,
        )
        cron_response = cron_llm.get_response_from_llm(
            prompt=frequency, use_cache=use_cache
        )
        if use_cache is False:
            logging.info(
                f"Cron generation LLM call - Elapsed: {cron_response.time_taken:.3f}s"
            )
        if cron_response.result.value == LLMResult.NOK.value:
            raise LLMHelperError(cron_response.output)
        output: str = cron_response.output
        return output

    @staticmethod
    def clear_cron_cache(cache_key_prefix: str) -> bool:
        cleared_count = 0
        cron_llm = LLMHelper(
            cache_key_prefix=cache_key_prefix,
            prompt_context=PromptContext.GENERATE_CRON_STRING,
        )
        cleared_count = cron_llm.clear_cache()
        if cleared_count == -1:
            return False
        return True
