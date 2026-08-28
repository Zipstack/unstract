"""Deterministic format/type validation for extracted values (QA, spec §9 check 2).

An empty value passes here (presence is the separate completeness check). For a
multivalued leaf each comma-separated element is validated against the format.
"""
import math
import re
from datetime import datetime
from typing import List, Optional

from .dataclasses import KeySpec

_NUMERIC_STRIP = re.compile(r"[,\s$%]")
_DATE_FORMATS = (
    "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y",
    "%B %d, %Y", "%b %d, %Y", "%m/%Y", "%Y",
)


def _is_number(value: str) -> bool:
    cleaned = _NUMERIC_STRIP.sub("", value)
    if cleaned in ("", "-", "."):
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _is_date(value: str) -> bool:
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


def _check_one(value: str, spec: KeySpec) -> bool:
    fmt = spec.format
    if fmt in ("number", "currency"):
        return _is_number(value)
    if fmt == "date":
        return _is_date(value)
    if fmt == "enum":
        return value.strip().casefold() in {e.casefold() for e in spec.enum_values}
    if fmt == "regex":
        try:
            return re.fullmatch(spec.regex_pattern, value.strip()) is not None
        except re.error:
            return True  # a broken author-supplied pattern should not fail extraction
    # "string" or any free-text hint: nothing to validate.
    return True


def validate_format(value: str, spec: KeySpec) -> bool:
    """True if `value` conforms to `spec.format`. Empty value -> True (completeness is
    checked separately). Multivalued -> every element must conform."""
    if value is None or value.strip() == "":
        return True
    if spec.multivalued:
        elements: List[str] = [e.strip() for e in value.split(",") if e.strip()]
        return all(_check_one(e, spec) for e in elements) if elements else True
    return _check_one(value, spec)


def coerce_number(value: str) -> Optional[float]:
    """Parse a numeric/currency string to a float, or None. Strips commas/spaces/$/%."""
    if value is None:
        return None
    cleaned = _NUMERIC_STRIP.sub("", value)
    if cleaned in ("", "-", "."):
        return None
    try:
        n = float(cleaned)
    except ValueError:
        return None
    # float() accepts 'inf'/'nan'/'1e400' as literals — reject non-finite so callers
    # (output normalization, constraint comparison) never see inf/nan.
    return n if math.isfinite(n) else None


def coerce_date(value: str) -> Optional[str]:
    """Parse a date string to ISO 'YYYY-MM-DD', or None."""
    if value is None:
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def coerce_enum(value: str, spec: KeySpec) -> "Optional[str]":
    """Return the canonical `spec.enum_values` element matching `value` case-insensitively, or None."""
    if value is None:
        return None
    cf = value.strip().casefold()
    for e in spec.enum_values:
        if e.casefold() == cf:
            return e
    return None
