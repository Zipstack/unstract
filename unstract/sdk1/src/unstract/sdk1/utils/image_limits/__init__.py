"""Model-aware limits for image output mode.

Image output mode sends every page image of a document to a vision LLM in
one request. Each provider caps such a request differently (image count,
request bytes, per-image bytes and pixels) and none of it is in litellm's
registry, so Unstract maintains the table in ``limits.json`` here.

Public surface:

- ``resolve_image_limits`` / ``resolve_image_limits_for_adapter`` — look up
  the limits for a provider/model (see ``resolve``).
- ``compute_page_budget`` / ``ImageModePolicy`` / ``check_page_set`` — turn
  limits into the checks the extraction and answer paths run (see
  ``policy``).
- ``get_limits_table`` — the effective table: override file, else the copy
  fetched from GitHub in the background, else the bundled copy (see
  ``source``). Never waits on the network.
- ``codes`` — the stable error-code strings.
"""

from unstract.sdk1.utils.image_limits._schema import (
    BUNDLED_LIMITS_PATH,
    LIMITS_OVERRIDE_FILE_ENV,
    LimitsSchemaError,
    LimitsTable,
    TableOrigin,
    load_limits_table,
)
from unstract.sdk1.utils.image_limits.policy import (
    ENFORCE_ENV,
    ImageModePolicy,
    ManyImagesRule,
    PageBudget,
    check_page_image,
    check_page_set,
    compute_page_budget,
    estimate_wire_bytes,
    extraction_bound_kwargs,
    fixed_cap_bound_kwargs,
    format_limit_source,
    model_aware_limits_enabled,
    page_cap_message,
    png_dimensions,
)
from unstract.sdk1.utils.image_limits.resolve import (
    ImageRequestLimits,
    LimitValue,
    local_max_input_tokens,
    provider_key,
    resolve_image_limits,
    resolve_image_limits_for_adapter,
)
from unstract.sdk1.utils.image_limits.source import (
    DEFAULT_LIMITS_URL,
    LIMITS_REFRESH_ENV,
    LIMITS_URL_ENV,
    clear_limits_cache,
    get_limits_table,
)

__all__ = [
    "BUNDLED_LIMITS_PATH",
    "DEFAULT_LIMITS_URL",
    "ENFORCE_ENV",
    "LIMITS_OVERRIDE_FILE_ENV",
    "LIMITS_REFRESH_ENV",
    "LIMITS_URL_ENV",
    "TableOrigin",
    "ImageModePolicy",
    "ImageRequestLimits",
    "ManyImagesRule",
    "LimitValue",
    "PageBudget",
    "check_page_image",
    "check_page_set",
    "compute_page_budget",
    "estimate_wire_bytes",
    "extraction_bound_kwargs",
    "fixed_cap_bound_kwargs",
    "format_limit_source",
    "page_cap_message",
    "png_dimensions",
    "LimitsSchemaError",
    "LimitsTable",
    "clear_limits_cache",
    "get_limits_table",
    "load_limits_table",
    "local_max_input_tokens",
    "model_aware_limits_enabled",
    "provider_key",
    "resolve_image_limits",
    "resolve_image_limits_for_adapter",
]
