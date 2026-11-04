"""Stable machine-readable error codes for image-output-mode limit failures.

Single home for the code strings. The executor formats both extraction and
answer errors as ``"CODE: message"`` because error propagation to Prompt
Studio and the deployment API is string-only; the cloud plugin reads them
through the bridge. Callers may prepend context (Prompt Studio's
``"Failed to extract '<file>'. "``), so a consumer must look for
``"CODE: "`` anywhere in the text rather than anchor on its start. Keep the
values stable: they are user-visible.
"""

# More pages than the model's budget allows (image count, LLMWhisperer's 999
# or an operator ceiling / the fixed cap; the context-window estimate never rejects).
IMAGE_PAGE_CAP_EXCEEDED = "IMAGE_PAGE_CAP_EXCEEDED"
# The page images together exceed the model's request-size limit.
IMAGE_PAGES_TOO_LARGE = "IMAGE_PAGES_TOO_LARGE"
# One page breaks a per-image byte or pixel limit (the message says whether
# splitting helps: see ``policy.page_too_large_message``).
IMAGE_PAGE_TOO_LARGE = "IMAGE_PAGE_TOO_LARGE"
# The provider rejected a request the local checks allowed (backstop).
IMAGE_REQUEST_TOO_LARGE = "IMAGE_REQUEST_TOO_LARGE"
# LLM ids were supplied but limits could not be resolved before conversion.
IMAGE_LIMITS_UNRESOLVED = "IMAGE_LIMITS_UNRESOLVED"
