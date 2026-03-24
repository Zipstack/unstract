import re

from rest_framework.serializers import ValidationError

# Pattern to detect HTML/script tags
HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
# Pattern to detect javascript: protocol
JS_PROTOCOL_PATTERN = re.compile(r"javascript\s*:", re.IGNORECASE)
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
        raise ValidationError(f"{field_name} must not contain JavaScript protocols.")
    if EVENT_HANDLER_PATTERN.search(value):
        raise ValidationError(f"{field_name} must not contain event handler attributes.")
    return value


def validate_name_field(value: str, field_name: str = "This field") -> str:
    """Validate name/identifier fields - no HTML tags, strip whitespace."""
    value = value.strip()
    if not value:
        raise ValidationError(f"{field_name} must not be empty.")
    return validate_no_html_tags(value, field_name)
