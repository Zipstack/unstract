import logging
import re
from typing import NoReturn

from rest_framework.serializers import ValidationError

logger = logging.getLogger(__name__)

# Only tags that can execute script or load remote content are rejected. A blanket
# "any angle bracket" rule cannot be used here: these validators run on free-form
# text (prompts, chat questions, descriptions) where "qty <threshold" and
# "the <invoice_no> field" are ordinary content, not markup.
_SCRIPTABLE_TAGS = (
    "script|iframe|object|embed|svg|math|link|meta|base|form|style|"
    "applet|frame|frameset|template"
)
HTML_TAG_PATTERN = re.compile(rf"<\s*/?\s*({_SCRIPTABLE_TAGS})\b", re.IGNORECASE)
# Pattern to detect dangerous URI protocols: javascript:, vbscript:, and the data:
# MIME types that can carry markup or script. Inert payloads such as
# "data:image/png;base64,..." are left alone, as is prose like "Input data: JSON".
JS_PROTOCOL_PATTERN = re.compile(
    r"(?:javascript|vbscript)\s*:|"
    r"data\s*:\s*(?:text/html|image/svg\+xml|"
    r"application/(?:xhtml\+xml|x?-?javascript|ecmascript))",
    re.IGNORECASE,
)
# Pattern to detect event handlers using a vetted list of DOM event names.
# This avoids false positives on benign words like "connection=", "onboarding=", etc.
_DOM_EVENTS = (
    "abort|blur|change|click|close|contextmenu|copy|cut|dblclick|drag|dragend|"
    "dragenter|dragleave|dragover|dragstart|drop|error|focus|focusin|focusout|"
    "input|invalid|keydown|keypress|keyup|load|mousedown|mouseenter|mouseleave|"
    "mousemove|mouseout|mouseover|mouseup|paste|pointerdown|pointerenter|"
    "pointerleave|pointermove|pointerout|pointerover|pointerup|reset|resize|"
    "scroll|select|submit|toggle|touchcancel|touchend|touchmove|touchstart|"
    "unload|wheel"
)
EVENT_HANDLER_PATTERN = re.compile(rf"\bon({_DOM_EVENTS})\s*=", re.IGNORECASE)


def _reject(field_name: str, reason: str, message: str) -> NoReturn:
    logger.warning(
        "input_validation_rejected",
        extra={"field": field_name, "reason": reason},
    )
    raise ValidationError(message)


def validate_no_html_tags(value: str, field_name: str = "This field") -> str:
    """Reject values containing HTML/script tags."""
    if HTML_TAG_PATTERN.search(value):
        _reject(
            field_name,
            "html_tag",
            f"{field_name} must not contain HTML or script tags.",
        )
    if JS_PROTOCOL_PATTERN.search(value):
        _reject(
            field_name,
            "js_protocol",
            f"{field_name} must not contain dangerous URI protocols.",
        )
    if EVENT_HANDLER_PATTERN.search(value):
        _reject(
            field_name,
            "event_handler",
            f"{field_name} must not contain event handler attributes.",
        )
    return value


def validate_name_field(value: str, field_name: str = "This field") -> str:
    """Validate name/identifier fields - no HTML tags, strip whitespace."""
    value = value.strip()
    if not value:
        raise ValidationError(f"{field_name} must not be empty.")
    return validate_no_html_tags(value, field_name)


# Allow-list of characters permitted in user-facing free text (names,
# descriptions). Unlike ``validate_no_html_tags`` (which block-lists known
# dangerous constructs), this is a strict allow-list: alphanumerics, spaces and
# a small set of common punctuation. Angle brackets (``<``/``>``), double
# quotes, ampersands and backticks are rejected, so a stored value cannot start
# a tag or break out of a double-quoted HTML attribute when rendered in
# non-React contexts (emails, PDFs, logs).
#
# The apostrophe IS allowed (names like "Client's Prod Key" are legitimate), so
# a single-quoted attribute context — ``title='{value}'`` — is NOT covered by
# this validator and must still escape the value at render time.
SAFE_TEXT_PATTERN = re.compile(r"^[a-zA-Z0-9 \-_.,:'()/]+$")
SAFE_TEXT_ERROR = (
    "Only alphanumeric characters, spaces, hyphens, underscores, "
    "periods, commas, colons, apostrophes, parentheses, and forward slashes "
    "are allowed."
)


def validate_safe_text(value: str) -> str:
    """Restrict free text to the safe allow-list in ``SAFE_TEXT_PATTERN``.

    Strips surrounding whitespace, rejects empty/whitespace-only input, and
    rejects any character outside the allow-list (which excludes ``<``, ``>``,
    double quotes, ``&``, backticks and similar injection-prone characters —
    but not the apostrophe). Returns the stripped value on success.
    """
    stripped = value.strip()
    if not stripped:
        raise ValidationError("This field cannot be empty.")
    if not SAFE_TEXT_PATTERN.match(stripped):
        raise ValidationError(SAFE_TEXT_ERROR)
    return stripped
