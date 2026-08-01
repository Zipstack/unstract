"""Shared input guards and output scrubbing for the MCP tool surface.

These sit above ``tools/`` rather than inside it because every tool module needs
them and none owns them. Parked in a tool module they were peers of their own
consumers, which forced function-local imports to dodge the resulting cycle —
the usual sign that a shared primitive is at the wrong layer.
"""

import logging
import re
import uuid
from typing import Any

from mcp_server.exceptions import MCPToolError

logger = logging.getLogger(__name__)

# How many rows a listing tool returns. Listings are read by an agent with a
# finite context, so an unbounded list is not more useful than a capped one —
# it just costs more and crowds out the rest of the conversation.
LIST_LIMIT = 100

_REDACTED = "[REDACTED]"

# Error text from a failed execution is one of the few places a secret can
# reach an agent without any tool asking for it: a connector that fails to
# connect may report the connection string it tried, and a provider client may
# echo the key it authenticated with. These patterns catch the common shapes.
#
# Each entry is (pattern, replacement). The replacement keeps the surrounding
# context — the key name, the URL prefix — so the message stays diagnosable
# while the value itself is gone.
_SECRET_PATTERNS = (
    # Bearer tokens first: "Authorization: Bearer <token>" would otherwise be
    # consumed by the key=value rule below, which would mask the word "Bearer"
    # and leave the token itself in place.
    (
        re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._\-]{8,})"),
        rf"\1{_REDACTED}",
    ),
    # key=value / key: value, where the key looks credential-ish. Stops at
    # whitespace, quote or delimiter so the rest of the message survives.
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|secret_access_key|access_key|"
            r"api[_-]?key|token|authorization|credential)"
            r"(\s*[=:]\s*)"
            r"([^\s,;'\"&)}\]]+)"
        ),
        rf"\1\2{_REDACTED}",
    ),
    # Credentials embedded in a URL: scheme://user:secret@host
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@]+)(@)"),
        rf"\1{_REDACTED}\3",
    ),
)

# Every pattern above requires one of these literals to match. Checking for them
# first lets ordinary text — which is nearly all of it — skip three regex passes
# that would each rebuild the whole string. This matters because
# ``redact_structure`` walks every string in an execution result, and with
# ``include_extracted_text`` that is the raw OCR text of every page, on the
# return path of a billable call. Measured ~7x faster on a 500KB body, and
# output-identical: a string containing none of these cannot match any pattern.
# ``test_redaction.SecretAnchorTest`` pins that equivalence.
#
# ``in`` on a str beats a combined regex alternation here — Python's regex
# engine does not do multi-literal search well.
_SECRET_ANCHORS = (
    "bearer",
    "password",
    "passwd",
    "pwd",
    "secret",
    "access_key",
    "apikey",
    "api_key",
    "api-key",
    "token",
    "authorization",
    "credential",
    "://",
)


def valid_uuid(value: str, field: str, hint: str) -> str:
    """Reject a malformed id before it reaches a UUID-typed ORM filter.

    Filtering a UUID column by an unparseable string raises Django's
    ``ValidationError`` from the field itself, *before* the ``is None`` check
    each call site writes — so the agent gets a generic failure instead of the
    actionable message the site already prepared, and on the preflight path it
    escaped the JSON-RPC envelope entirely.

    Returns the value unchanged so it can be used inline.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise MCPToolError(
            f"'{value}' is not a valid {field}. Expected a UUID. {hint}"
        ) from error
    return value


def redact_secrets(text: str | None) -> str | None:
    """Mask credential-shaped substrings in free-form text.

    Applied to the free-form error fields the observability tools read off
    execution records (``error_message``, ``execution_error``), and — via
    ``redact_structure`` — to upstream payloads that this app does not itself
    assemble field by field.

    **``MCPToolError`` messages are not automatically redacted.** A raise site
    interpolating upstream text — ``raise MCPToolError(f"...{error}")`` — must
    call this itself; the transport returns that message to the agent verbatim.

    This is a safety net, not a guarantee — it cannot recognise a secret that
    looks like ordinary prose — so it complements the rule that structured
    fields are named explicitly rather than replacing it.
    """
    if not text:
        return text

    # Cheap literal pre-filter; see _SECRET_ANCHORS for why this is safe.
    lowered = text.lower()
    if not any(anchor in lowered for anchor in _SECRET_ANCHORS):
        return text

    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_structure(value: Any) -> Any:
    """Apply ``redact_secrets`` to every string inside a nested structure.

    Most tools serialize named fields, so what they return is known. The ones
    that **delegate** do not: the Prompt Studio tools, ``executePipeline`` and
    ``extractDocument`` hand back whatever the view or execution helper produced
    — ``response.data`` including non-2xx error bodies, and raw execution
    results — which can carry a failed connector's error text verbatim. Those
    paths get the same net the error fields get. (``setApiDeploymentActive`` and
    ``setPipelineActive`` write too, but build named fields, so they do not.)

    Containers are rebuilt rather than mutated, so a caller's queryset row or
    cached dict is never altered as a side effect of being reported. Sequences
    come back as plain lists — see the comment below for why the input subclass
    is deliberately not preserved.
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: redact_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        # Plain containers, deliberately not `type(value)(...)`. Rebuilding the
        # exact subclass breaks on anything whose __init__ is not "an iterable":
        # DRF's ReturnList requires a `serializer` kwarg, and a namedtuple takes
        # positional fields. Either would raise here — on the *return* path of a
        # billable tool, after the budget was spent and the upstream work paid
        # for. The result is json.dumps-ed by the transport, so the subclass buys
        # nothing.
        return [redact_structure(item) for item in value]
    return value


def truncation_note(shown: int, total: int) -> dict[str, Any]:
    """Describe a capped listing, or nothing when it was complete.

    Silent truncation would read to an agent as "this is everything", which is
    exactly the sort of wrong premise it would then build on.
    """
    if total <= shown:
        return {}
    return {
        "truncated": True,
        "note": (
            f"Showing {shown} of {total}. Narrow the question or use the "
            "Unstract UI to see the rest."
        ),
    }
