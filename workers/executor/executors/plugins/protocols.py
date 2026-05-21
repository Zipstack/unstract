"""Protocol classes defining contracts for cloud executor plugins.

Cloud plugins must satisfy these protocols.  The OSS repo never imports
cloud code — only these protocols and ``ExecutorPluginLoader.get(name)``
are used to interact with plugins.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HighlightDataProtocol(Protocol):
    """Cross-cutting: source attribution from LLMWhisperer metadata.

    Matches the cloud ``HighlightData`` plugin constructor which
    accepts ``enable_word_confidence`` (not ``execution_source``).
    The filesystem instance is determined by the caller and passed in.
    """

    def __init__(
        self,
        file_path: str,
        fs_instance: Any = None,
        enable_word_confidence: bool = False,
        **kwargs: Any,
    ) -> None: ...

    def run(
        self,
        response: Any = None,
        is_json: bool = False,
        original_text: str = "",
        **kwargs: Any,
    ) -> dict: ...

    @staticmethod
    def extract_word_confidence(original_text: str, is_json: bool = False) -> dict: ...


@runtime_checkable
class ChallengeProtocol(Protocol):
    """Legacy executor: quality verification with a second LLM."""

    def run(self) -> None: ...


@runtime_checkable
class EvaluationProtocol(Protocol):
    """Legacy executor: prompt evaluation."""

    def run(self, **kwargs: Any) -> dict: ...


@runtime_checkable
class LookupEnrichmentProtocol(Protocol):
    """Legacy executor: post-extraction lookup enrichment.

    The executor calls ``run_with_metrics`` (not ``run``) because the
    plugin returns an outcome object exposing ``usage_records`` and
    ``llm_metrics`` for the calling executor to flush. ``METRICS_KEY``
    keys the lookup metrics into the per-prompt metrics dict.
    """

    METRICS_KEY: str

    def run_with_metrics(
        self,
        *,
        llm_cls: Any,
        lookup_config: dict,
        structured_output: dict,
        current_value: Any,
        metadata: dict,
        prompt_name: str,
        shim: Any,
        usage_kwargs: dict | None = None,
    ) -> Any: ...
