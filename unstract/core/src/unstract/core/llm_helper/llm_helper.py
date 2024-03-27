import logging
import os
import time
from typing import Optional

from llama_index.llms import AzureOpenAI

from unstract.core.llm_helper.config import AzureOpenAIConfig
from unstract.core.llm_helper.enums import LLMResult, PromptContext
from unstract.core.llm_helper.llm_cache import LLMCache
from unstract.core.llm_helper.models import LLMResponse

logger = logging.getLogger(__name__)


class LLMHelper:
    """Helps generate response from an LLM for a given prompt.

    It can leverage a prompt context if necessary.
    """

    def __init__(
        self,
        prompt_template: str = "azure-open-ai/version-0.1",
        cache_key_prefix: Optional[str] = None,
        prompt_context: Optional[PromptContext] = None,
    ) -> None:
        self.prompt_template = prompt_template
        self.prompt_context = prompt_context
        self.prompt = ""
        self.cache_key_prefix = "cache:"
        if cache_key_prefix:
            self.cache_key_prefix += cache_key_prefix + ":"
        if prompt_context:
            with open(
                f"{os.path.dirname(__file__)}/static/prompts/{prompt_template}/{prompt_context}",  # noqa
            ) as file:
                self.prompt = file.read()
            self.cache_key_prefix += prompt_context + ":"

        self.llm_cache = LLMCache(cache_key_prefix=self.cache_key_prefix)

    def _prepare_prompt(self, user_prompt: str) -> str:
        """Used to add context to the user entered prompt."""
        if not self.prompt:
            return user_prompt
        prompt_for_model = self.prompt

        if self.prompt_context == PromptContext.GENERATE_CRON_STRING:
            prompt_for_model = prompt_for_model.replace(
                "{$user_prompt}", user_prompt
            )

        return prompt_for_model

    def get_response_from_llm(
        self, prompt: str, use_cache: bool = False
    ) -> LLMResponse:
        """Responds with the LLM output for a given prompt.

        Args:
            prompt (str): Prompt to generate response for
            use_cache (bool, optional): Flag to retrieve from cache. Defaults to False.

        Returns:
            LLMResponse: LLM output
        """
        prompt_for_model = self._prepare_prompt(user_prompt=prompt)
        ai_service = self.prompt_template.split("/")[0]
        if ai_service == "azure-open-ai":
            logger.info("Using Azure OpenAI")
            if use_cache:
                response = self.llm_cache.get_for_prompt(
                    prompt=prompt_for_model
                )
                if response:
                    return LLMResponse(
                        result=LLMResult.OK, output=response, cost_type="cache"
                    )
                else:
                    logger.warning("Will call OpenAI API")
            start_time = time.time()

            try:
                azure_openai_config = AzureOpenAIConfig.from_env()
                llm = AzureOpenAI(
                    model=azure_openai_config.model,
                    deployment_name=azure_openai_config.deployment_name,
                    engine=azure_openai_config.engine,
                    api_key=azure_openai_config.api_key,
                    api_version=azure_openai_config.api_version,
                    azure_endpoint=azure_openai_config.azure_endpoint,
                    api_type=azure_openai_config.api_type,
                    temperature=0,
                    max_retries=10,
                )
                resp = llm.complete(prompt_for_model)
            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                return LLMResponse(
                    result=LLMResult.NOK,
                    output=f"OpenAI error: {e}",
                    cost_type=ai_service,
                )
            end_time = time.time()
            resp = resp.text
            logger.info(f"OpenAI Response: {resp}")
            time_taken = end_time - start_time

            self.llm_cache.set_for_prompt(
                prompt=prompt_for_model, response=resp
            )
            return LLMResponse(
                output=resp, cost_type=ai_service, time_taken=time_taken
            )
        else:
            logger.error(f"AI service '{ai_service}' not found")
        return LLMResponse(
            result=LLMResult.NOK,
            output=f"AI service '{ai_service}' not found",
            cost_type=ai_service,
        )

    def clear_cache(self) -> int:
        """Clears the cached responses by using the prefix.

        Returns:
            int: Number of cache entries deleted, -1 if it failed
        """
        return self.llm_cache.clear_by_prefix()
