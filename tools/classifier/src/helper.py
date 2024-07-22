from typing import Any, Optional

from unstract.sdk.cache import ToolCache
from unstract.sdk.constants import ToolEnv
from unstract.sdk.llm import LLM
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.utils import ToolUtils
from unstract.sdk.x2txt import TextExtractionResult, X2Text


class ClassifierHelper:
    """Helper functions for Classifier."""

    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool

    def extract_text(
        self, file: str, text_extraction_adapter_id: Optional[str]
    ) -> Optional[str]:
        """Extract text from file.

        Args:
            file (str): The path to the input file

        Returns:
            str: page content
        """
        if not text_extraction_adapter_id:
            return self._extract_from_file(file)

        return self._extract_from_adapter(file, text_extraction_adapter_id)

    def _extract_from_adapter(self, file: str, adapter_id: str) -> Optional[str]:
        """Extract text from adapter.

        Args:
            file: The path to the input file
            adapter_id: The id of the adapter
        Returns:
            str: page content
        """
        self.tool.stream_log(
            "Creating text extraction adapter " f"using adapter_id: {adapter_id}"
        )
        x2text = X2Text(tool=self.tool, adapter_instance_id=adapter_id)

        self.tool.stream_log("Text extraction adapter has been created successfully.")
        self.tool.stream_log("Adapter created")

        try:
            extraction_result: TextExtractionResult = x2text.process(
                input_file_path=file
            )
            extracted_text: str = extraction_result.extracted_text
            return extracted_text
        except Exception as e:
            self.tool.stream_log(f"Adapter error: {e}")
            return None

    def _extract_from_file(self, file: str) -> Optional[str]:
        """Extract text from file.

        Args:
            file: The path to the input file
        Returns:
            str: page content
        """
        self.tool.stream_log("Extracting text from file")
        try:
            with open(file, "rb") as f:
                text = f.read().decode("utf-8")
        except Exception as e:
            self.tool.stream_log(f"File error: {e}")
            return None

        self.tool.stream_log("Text extracted from file")
        return text

    def find_classification(
        self,
        use_cache: bool,
        settings_string: str,
        bins: list[str],
        prompt: str,
        llm: LLM,
    ) -> Optional[str]:
        """Find classification for text.
        Args:
            use_cache (bool): Whether to use cache
            settings_string (str): hash of settings
            prompt (str): Prompt
            bins (list[str]): Classification Bins
            llm (LLM): LLM

        Returns:
            Optional[str]: Classification or None if not found in cache.
            If found in cache, returns the classification from the cache.
            If not found in cache, calls the LLM and returns the
            classification.
        """
        classification = None
        cache_key = None
        if use_cache:
            cache_key = (
                f"cache:{self.tool.workflow_id}:"
                f"{ToolUtils.hash_str(settings_string)}:"
                f"{ToolUtils.hash_str(prompt)}"
            )
            classification = self.get_result_from_cache(cache_key=cache_key)

        if classification is None:
            self.tool.stream_log("No classification found in cache, calling LLM.")
            classification = self.call_llm(prompt=prompt, llm=llm)
        if not classification:
            classification = "unknown"
        classification = classification.strip().lower()
        bins = [bin.lower() for bin in bins]
        if classification not in bins:
            self.tool.stream_error_and_exit(
                f"Invalid classification done: {classification}"
            )
        return classification

    def call_llm(self, prompt: str, llm: LLM) -> Optional[str]:
        """Call LLM.

        Args:
            prompt (str): Prompt
            llm (LLM): LLM

        Returns:
            str: Classification
        """
        try:
            completion = llm.complete(prompt)[LLM.RESPONSE]
            classification: str = completion.text.strip()
            self.tool.stream_log(f"LLM response: {completion}")
            return classification
        except Exception as e:
            self.tool.stream_error_and_exit(f"Error calling LLM {e}")
            return None

    def get_result_from_cache(self, cache_key: str) -> Optional[str]:
        """Get result from cache.

        Args:
            cache_key (str): key

        Returns:
            Optional[str]: result
        """
        cache = ToolCache(
            tool=self.tool,
            platform_host=self.tool.get_env_or_die(ToolEnv.PLATFORM_HOST),
            platform_port=int(self.tool.get_env_or_die(ToolEnv.PLATFORM_PORT)),
        )
        cached_response: Optional[str] = cache.get(cache_key)
        if cached_response is not None:
            classification = cached_response
            self.tool.stream_cost(cost=0.0, cost_units="cache")
            return classification
        return None

    def save_result_to_cache(self, cache_key: str, result: Any) -> None:
        """Save result to cache.

        Args:
            cache_key (str): key
            result (Any): result to save in cache
        Returns:
            None: None
        """
        cache = ToolCache(
            tool=self.tool,
            platform_host=self.tool.get_env_or_die(ToolEnv.PLATFORM_HOST),
            platform_port=int(self.tool.get_env_or_die(ToolEnv.PLATFORM_PORT)),
        )
        cache.set(cache_key, result)
