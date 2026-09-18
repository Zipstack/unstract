r"""Shared JSON encoding for Postgres ``jsonb`` columns.

``json.dumps`` accepts several values that Postgres ``jsonb`` then rejects at
insert time, because ``jsonb`` *parses* what it is given and stores strings as
``text``:

- a **NUL** (``U+0000``) in a string — encoded as ``\u0000``, which ``jsonb``
  refuses with ``unsupported Unicode escape sequence`` (``text`` cannot hold a
  NUL). Real documents carry these: LLMWhisperer's ``native_text`` mode returns
  a PDF's embedded text layer verbatim, NUL bytes included, and the value then
  travels through the prompt into the extracted output.
- an **unpaired surrogate** (``U+D800``-``U+DFFF`` with no partner) — encoded as
  ``\udXXX``, refused the same way. A *well-formed* high+low pair is fine and is
  preserved: Postgres combines it into the astral character it encodes.
- **NaN / Infinity / -Infinity** — Python's lenient default emits these as bare
  tokens, which are not JSON at all and which ``jsonb`` refuses.

Every one of those is a *permanent* failure: the insert can never succeed, so a
writer that lets it escape loses the payload. This module is the single place
that knows the rule, so each ``jsonb`` writer does not re-derive it — the PG
queue has three (the backend producer, the workers' barrier and the workers'
result backend) and they previously carried three different, partial defences.

It has no Django / psycopg / SDK dependency, so it lives in ``unstract.core``
where both trees import it — the same arrangement as :mod:`unstract.core.polling`.

Strings are *repaired* (the offending code points are dropped): a NUL or an
unpaired surrogate carries no meaning a caller wants, and discarding a whole
extracted result over one stray control byte is the worse outcome. Numbers are *not*
repaired — ``NaN`` has no correct ``jsonb`` spelling, and silently turning it
into ``null`` or ``0`` would corrupt a value rather than clean it, so
``allow_nan=False`` is enforced and the caller decides what a broken number means.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["JSONB_UNSAFE_RE", "dumps_for_jsonb", "sanitize_for_jsonb"]

# Exactly what `jsonb` will not store in a text value: a NUL, and any UNPAIRED
# surrogate.
#
# A *well-formed* high+low pair must be preserved — Postgres accepts it and
# combines it into the astral character it encodes (verified against a live
# server: '{"a": "😀"}'::jsonb -> {"a": "😀"}). A plain
# [\ud800-\udfff] class would match both halves of that pair and delete an emoji
# from an extracted result, which is the silent corruption this module exists to
# avoid. Only the halves that cannot pair are unsafe.
#
# Other C0 controls (\x01-\x1f) are legal in jsonb and are deliberately left
# alone — they are escaped on the way in and round-trip fine.
JSONB_UNSAFE_RE = re.compile(
    "\x00"
    "|[\ud800-\udbff](?![\udc00-\udfff])"  # high surrogate, no low following it
    "|(?<![\ud800-\udbff])[\udc00-\udfff]"  # low surrogate, no high preceding it
)


def sanitize_for_jsonb(value: Any) -> Any:
    """Return *value* with every string made storable in a ``jsonb`` column.

    Walks dicts, lists and tuples and strips the code points ``jsonb`` rejects
    (see :data:`JSONB_UNSAFE_RE`) from every string, keys included — a NUL is as
    fatal in a key as in a value. Anything else (numbers, ``None``, booleans, and
    objects a caller's ``default=`` hook will later coerce, such as ``UUID``) is
    returned untouched.

    Containers are rebuilt only as far as needed; the input is never mutated.
    Tuples come back as lists, which is what ``json.dumps`` would have produced
    anyway.
    """
    if isinstance(value, str):
        return JSONB_UNSAFE_RE.sub("", value)
    if isinstance(value, dict):
        return {sanitize_for_jsonb(k): sanitize_for_jsonb(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_jsonb(item) for item in value]
    return value


def dumps_for_jsonb(value: Any, *, default: Any = None) -> str:
    """Encode *value* as JSON text that a ``%s::jsonb`` cast will accept.

    Sanitises strings via :func:`sanitize_for_jsonb`, then encodes with
    ``allow_nan=False`` so ``NaN``/``Infinity`` raise a ``ValueError`` here — at
    the writer, with the caller's own error handling in reach — instead of
    surfacing later as a ``DataError`` from the database.

    Args:
        value: The object to encode.
        default: Optional ``json.dumps`` fallback for objects it cannot encode
            (e.g. ``str`` to coerce ``UUID``/``datetime``).

    Returns:
        JSON text safe to cast to ``jsonb``.

    Raises:
        ValueError: The value contains ``NaN``/``Infinity`` (or, without a
            *default*, is not JSON-serialisable).
        TypeError: The value is not JSON-serialisable and *default* did not
            handle it.
    """
    return json.dumps(sanitize_for_jsonb(value), default=default, allow_nan=False)
