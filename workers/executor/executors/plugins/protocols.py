"""Protocol classes defining contracts for cloud executor plugins.

Cloud plugins must satisfy these protocols.  The OSS repo never imports
cloud code — only these protocols and ``ExecutorPluginLoader.get(name)``
are used to interact with plugins.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HighlightDataProtocol(Protocol):
    """Cross-cutting: source attribution from LLMWhisperer metadata."""

    def __init__(
        self,
        file_path: str,
        fs_instance: Any,
        execution_source: str = "",
        **kwargs: Any,
    ) -> None: ...

    def run(self, response: str, is_json: bool = False, **kwargs: Any) -> dict: ...

    def get_highlight_data(self) -> Any: ...

    def get_confidence_data(self) -> Any: ...

    def extract_word_confidence(self, **kwargs: Any) -> dict: ...


@runtime_checkable
class ChallengeProtocol(Protocol):
    """Legacy executor: quality verification with a second LLM."""

    def run(self) -> None: ...


@runtime_checkable
class EvaluationProtocol(Protocol):
    """Legacy executor: prompt evaluation."""

    def run(self, **kwargs: Any) -> dict: ...
