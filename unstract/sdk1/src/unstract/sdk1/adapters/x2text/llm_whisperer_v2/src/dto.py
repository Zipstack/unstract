from dataclasses import dataclass


@dataclass
class WhispererRequestParams:
    """DTO for LLM Whisperer API request parameters.

    Args:
        tag (Optional[Union[str, List[str]]]): Tag value. Can be initialized with List[str] or str.
             Will be converted to str or None after initialization.
        enable_highlight (bool): Whether to enable highlighting. Defaults to False.
    """

    # TODO: Extend this DTO to include all Whisperer API parameters
    tag: str | list[str] | None = None
    enable_highlight: bool = False

    def __post_init__(self) -> None:
        # TODO: Allow list of tags once it's supported in LLMW v2
        if isinstance(self.tag, list):
            self.tag = self.tag[0] if self.tag else None
