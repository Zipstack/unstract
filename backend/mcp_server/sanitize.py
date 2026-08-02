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

# Every pattern above requires one of these literals to match, so text without
# any of them can skip three regex passes that would each rebuild the whole
# string. ``redact_structure`` walks every string in an execution result, so on
# short error messages — the common case — this is most of the work avoided.
#
# **The equivalence holds for ASCII text only, and the filter is gated on that.**
# ``(?i)`` and ``str.lower()`` are different case-folding functions: Python's
# regex engine folds U+017F (ſ) to "s" and U+212A (K) to "k", while ``.lower()``
# leaves both unchanged. So ``"paſſword=hunter2"`` matches pattern 2 but contains
# no anchor once lowercased — skipping the regexes there would leak the secret.
# For ASCII input the two agree, which is what makes the fast path sound; any
# non-ASCII string takes the full regex path. ``test_redaction.SecretAnchorTest``
# pins both halves.
#
# Measured on a 500KB body: ~8x faster when pure ASCII, but **~1x as soon as a
# single non-ASCII character appears anywhere in the string**, since that flips
# the whole body onto the regex path. That is the honest cost of correctness
# here: the payload this most wants to help — ``include_extracted_text`` OCR
# output, which realistically carries accents and curly quotes — is largely the
# case that does not benefit. The gate stays regardless; a leaked credential is
# not worth 60ms.
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


# Dict keys whose value is a credential regardless of how it is formatted.
# Same vocabulary as the key=value pattern above, kept as its own tuple because
# this matches a whole key rather than a substring of free text: matching
# loosely here would redact an ordinary field like "token_count".
_SECRET_KEY_NAMES = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "secret_access_key",
        "access_key",
        "access_key_id",
        "apikey",
        # Hyphens are normalised to underscores before lookup, so "api-key"
        # matches via this entry rather than needing its own.
        "api_key",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "authorization",
        "credential",
        "credentials",
        "private_key",
        "client_secret",
    }
)


def _normalise_key(key: str) -> str:
    """Fold a field name to snake_case for lookup.

    camelCase has to be split *before* lowercasing, or the words run together:
    ``secretAccessKey`` would become ``secretaccesskey`` and match nothing.
    That matters because AWS-style credentials arrive camelCased in exactly the
    upstream JSON these tools pass through — ``secretAccessKey``,
    ``accessKeyId``, ``clientSecret`` — so the compressed form was the common
    case rather than an exotic one.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key.strip())
    return spaced.lower().replace("-", "_").replace(" ", "_")


def _is_secret_key(key: str) -> bool:
    """True when a dict key names a credential.

    Exact match on a normalised key, not a substring test: ``token_count`` and
    ``has_credentials`` are ordinary fields an agent needs, and redacting them
    would make output harder to act on without making it safer.
    """
    return _normalise_key(key) in _SECRET_KEY_NAMES


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

    # Cheap literal pre-filter, ASCII-only — see _SECRET_ANCHORS for why the
    # isascii() gate is load-bearing rather than defensive.
    if text.isascii():
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

    Two mechanisms, because upstream payloads carry credentials in two shapes:
    free text where ``redact_secrets``'s patterns anchor on a delimiter
    (``"connect failed: password=x"``), and structured fields where the *key*
    names the secret and the value is bare (``{"api_key": "sk-x"}``). The
    second is the ordinary shape of serializer output — the exact thing the
    delegating tools hand back — and text scrubbing alone does not see it.

    Containers are rebuilt rather than mutated, so a caller's queryset row or
    cached dict is never altered as a side effect of being reported. Sequences
    come back as plain lists — see the comment below for why the input subclass
    is deliberately not preserved.
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        # A credential-named *key* whose value is a bare secret has no
        # delimiter for the text patterns to anchor on — `{"api_key": "sk-x"}`
        # is not the string `api_key=sk-x` — so the key name is what marks it.
        # This is the ordinary shape of serializer output, which is exactly
        # what the delegating tools return, so text scrubbing alone left the
        # most likely case uncovered.
        return {
            key: _REDACTED
            if isinstance(key, str) and _is_secret_key(key) and isinstance(item, str)
            else redact_structure(item)
            for key, item in value.items()
        }
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


def log_exception(log: logging.Logger, message: str, error: BaseException) -> None:
    """Log an upstream exception without piping its secrets into the log.

    ``logger.exception(f"...: {error}")`` writes the exception text *and* a
    traceback, both unredacted. That is a real exposure on these paths: the
    exceptions being logged come from connectors, provider clients and the
    execution stack, and a failed connection reports the string it tried. Logs
    are shipped to aggregation, so a secret there outlives the request and
    reaches an audience the credential was never scoped to.

    So the message is redacted, and the traceback is deliberately **not**
    attached: ``redact_secrets`` can only clean the string it is given, while a
    traceback renders frame locals — the very place a connection string or key
    sits. Losing the stack is the cost; the exception type and redacted message
    are kept, which is what identifies the failure. Where a stack is genuinely
    needed, log it separately from a site that controls what the exception
    holds.
    """
    log.error(f"{message}: {type(error).__name__}: {redact_secrets(str(error))}")
