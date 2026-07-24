import re

from rest_framework.serializers import ValidationError

# Pattern to detect HTML/script tags (closed tags and unclosed tags starting with a letter)
# The second alternative catches unclosed tags like "<script" or "<img src=x" that could
# be completed by adjacent content in non-React rendering contexts (emails, PDFs, logs)
HTML_TAG_PATTERN = re.compile(r"<[^>]*>|<[a-zA-Z/!]")
# Pattern to detect dangerous URI protocols: javascript:, vbscript:, and data: URIs.
# data: URIs are only matched when followed by a MIME type (word/word) to avoid
# false positives on ordinary English text like "Input data: JSON format".
JS_PROTOCOL_PATTERN = re.compile(
    r"(?:javascript|vbscript)\s*:|data\s*:\s*\w+/\w+", re.IGNORECASE
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


def validate_no_html_tags(value: str, field_name: str = "This field") -> str:
    """Reject values containing HTML/script tags."""
    if HTML_TAG_PATTERN.search(value):
        raise ValidationError(f"{field_name} must not contain HTML or script tags.")
    if JS_PROTOCOL_PATTERN.search(value):
        raise ValidationError(f"{field_name} must not contain dangerous URI protocols.")
    if EVENT_HANDLER_PATTERN.search(value):
        raise ValidationError(f"{field_name} must not contain event handler attributes.")
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
