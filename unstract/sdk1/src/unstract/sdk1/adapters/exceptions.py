from unstract.sdk1.exceptions import SdkError


# TODO: Remove redundant AdapterError classes and use SdkError itself
class AdapterError(SdkError):
    pass


class LLMError(AdapterError):
    pass


class ExtractorError(AdapterError):
    pass


class ImageLimitExceededError(ExtractorError):
    """An image-mode document breaks the LLM's request limits at extraction.

    Carries a stable ``error_code`` (see ``unstract.sdk1.utils.image_limits.codes``)
    so callers can surface it, and ``charged`` so the message and the caller
    can be honest about whether LLMWhisperer already billed the conversion.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        charged: bool | None,
        status_code: int = 400,
    ) -> None:
        """Record the stable code and whether the conversion was billed."""
        super().__init__(message, status_code=status_code)
        self.error_code = error_code
        self.charged = charged
