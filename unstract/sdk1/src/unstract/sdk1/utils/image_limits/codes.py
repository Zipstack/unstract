"""Stable machine-readable error codes for image-output-mode limit failures.

Single home for the code strings. The executor bridge prefixes them onto
error messages (``"CODE: message"``) because error propagation to Prompt
Studio and the deployment API is string-only; the cloud plugin reads them
through the bridge. Keep the values stable: they are user-visible.
"""

# More pages than the model's budget allows (image count or context term).
IMAGE_PAGE_CAP_EXCEEDED = "IMAGE_PAGE_CAP_EXCEEDED"
# The page images together exceed the model's request-size limit.
IMAGE_PAGES_TOO_LARGE = "IMAGE_PAGES_TOO_LARGE"
# One page breaks a per-image byte or pixel limit; splitting does not help.
IMAGE_PAGE_TOO_LARGE = "IMAGE_PAGE_TOO_LARGE"
# The provider rejected a request the local checks allowed (backstop).
IMAGE_REQUEST_TOO_LARGE = "IMAGE_REQUEST_TOO_LARGE"
# LLM ids were supplied but limits could not be resolved before conversion.
IMAGE_LIMITS_UNRESOLVED = "IMAGE_LIMITS_UNRESOLVED"
