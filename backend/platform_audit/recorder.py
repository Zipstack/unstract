"""Record platform audit events.

:func:`record_platform_event` is the only way an event is written, and it is
best-effort by contract: it never raises and never fails the request that
called it. A failure is logged and the event is lost. Failures are logged by
:func:`describe_exception`: type, SQLSTATE and where it was raised, never the
exception's message, which can echo the values (e-mails, row data) it was
given.

The write is deferred with ``transaction.on_commit``, so an event is stored only
if the change it describes is committed. When the caller is not inside a
transaction (the default here: ``ATOMIC_REQUESTS`` is off) ``on_commit`` runs the
write straight away. Inside a transaction (``ATOMIC_REQUESTS``, or a view's own
``atomic()``) an event recorded from a ``best_effort`` helper is dropped if that
helper later raises, because its savepoint rolls back. Everything the write needs is resolved at call time, so
the deferred write does not depend on request state that may be gone by then.

Call it after the change has succeeded, never before::

    record_platform_event(
        action=Action.KEY_ROTATED,
        target_type=TargetType.PLATFORM_API_KEY,
        target_id=key.id,
        target_name=key.name,
        request=request,
    )
"""

import contextlib
import logging
import os
import sysconfig
import traceback
from collections.abc import Callable, Mapping
from functools import partial, wraps
from typing import Any, ParamSpec, TypeVar

from account_v2.models import Organization, User
from django.db import transaction
from django.utils import timezone
from log_request_id import local as request_id_local
from utils.user_context import UserContext

from platform_audit.actions import get_action
from platform_audit.models import ActorType, PlatformAuditEvent

logger = logging.getLogger(__name__)

#: Appended to a summary when the previous value could not be read, so such an
#: event reads the same whichever emitter wrote it.
BEFORE_UNAVAILABLE = "(previous value unavailable)"

P = ParamSpec("P")
T = TypeVar("T")


def record_platform_event(
    *,
    action: str,
    target_type: str,
    target_id: Any = "",
    target_name: str = "",
    request: Any = None,
    actor: User | None = None,
    changes: Mapping[str, Any] | None = None,
    summary: str = "",
    metadata: Mapping[str, Any] | None = None,
    organization: Organization | None = None,
) -> None:
    """Record one platform event. Never raises.

    Args:
        action: A registered key (see ``platform_audit.actions``).
        target_type: What was changed, e.g. ``TargetType.GROUP``.
        target_id: Its id; stored as a string.
        target_name: Its display name at the time of the change.
        request: The request that made the change. Supplies the actor
            (including the platform API key, when one was used), the request
            id and, through ``UserContext``, the organisation.
        actor: The acting user when there is no request (or to override it).
            With neither, the actor is ``system``.
        changes: ``{"before": {...}, "after": {...}}``. Never put secrets here.
        summary: One line for the Audit log row, e.g. ``"was unstract_user"``.
        metadata: Extra detail kept on the row but not part of the read API.
        organization: Defaults to the organisation in ``UserContext``.
    """
    try:
        # Its reads (organisation, actor, key) run in the caller's transaction;
        # a savepoint keeps a failed one from aborting it (see best_effort).
        with _savepoint():
            action = str(action)
            if get_action(action) is None:
                # A programming error, and it drops every event from that emitter.
                logger.error(
                    "Platform audit: unregistered action %r not recorded", action
                )
                return
            organization = organization or UserContext.get_organization()
            if organization is None:
                logger.warning(
                    "Platform audit: no organisation in context, %r not recorded", action
                )
                return
            fields = {
                "organization": organization,
                "occurred_at": timezone.now(),
                "action": action,
                "target_type": _clip(target_type, 64),
                "target_id": _clip(target_id, 255),
                "target_name": _clip(target_name, 255),
                "summary": str(summary or ""),
                "changes": _normalise_changes(changes, action),
                "metadata": dict(metadata or {}),
                "request_id": _clip(_request_id(request), 64),
                **_resolve_actor(request=request, actor=actor),
            }
            transaction.on_commit(partial(_write, fields), robust=True)
    except Exception as exc:
        # Not logger.exception: its message can echo row data (describe_exception).
        logger.error(  # NOSONAR
            "Platform audit: failed to record %r (%s)", action, describe_exception(exc)
        )


def _savepoint() -> contextlib.AbstractContextManager:
    if transaction.get_connection().in_atomic_block:
        return transaction.atomic()
    return contextlib.nullcontext()


def best_effort(fn: Callable[P, T]) -> Callable[P, T | None]:
    """Make an audit helper unable to fail the request that calls it.

    Instrumented views read "before" values ahead of the change they audit and
    build events after it. Decorate those helpers: an error is logged and the
    helper returns ``None``.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
        try:
            if not transaction.get_connection().in_atomic_block:
                return fn(*args, **kwargs)
            # Inside a transaction (ATOMIC_REQUESTS): a savepoint, so a failed
            # query here cannot leave the view's own transaction aborted.
            # Outside one there is nothing to protect, and opening a
            # transaction would defer the helper's on_commit writes and hold a
            # connection across any network call it makes.
            with transaction.atomic():
                return fn(*args, **kwargs)
        except Exception as exc:
            # Not logger.exception: see describe_exception.
            logger.error(  # NOSONAR
                "Platform audit: %s failed (%s)",
                fn.__qualname__,
                describe_exception(exc),
            )
            return None

    return wrapper


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, dict]:
    """Keep only the keys whose value changed, as ``{"before", "after"}``."""
    changed = [k for k in after if before.get(k) != after.get(k)]
    return {
        "before": {k: before.get(k) for k in changed},
        "after": {k: after.get(k) for k in changed},
    }


def _write(fields: dict[str, Any]) -> None:
    try:
        with transaction.atomic():
            PlatformAuditEvent.objects.create(**fields)
    except Exception as exc:
        # Enough to tell which change went unaudited: no changes, metadata or
        # e-mail, and not the exception's message (see describe_exception).
        logger.error(  # NOSONAR
            "Platform audit: failed to write %r (%s; org=%s "
            "target=%s:%s actor=%s:%s key=%s request_id=%s)",
            fields.get("action"),
            describe_exception(exc),
            getattr(fields.get("organization"), "organization_id", None),
            fields.get("target_type"),
            _loggable_id(fields.get("target_id")),
            fields.get("actor_type"),
            getattr(fields.get("actor"), "pk", None),
            fields.get("actor_key_id"),
            fields.get("request_id"),
        )


def describe_exception(exc: BaseException) -> str:
    """Type, SQLSTATE and the app frames that raised it, without the message.

    A database error's message can echo the row it rejected ("Failing row
    contains ..."), and an identity-provider error can echo the e-mail it was
    sent, so the message is never logged. Django raises database errors
    ``from`` the driver's, which carries the SQLSTATE as ``pgcode``.
    """
    cause = exc.__cause__ or exc
    frames = traceback.extract_tb(exc.__traceback__)
    # Library frames (Django, the driver) say little about which change
    # failed; keep the app's own, innermost last, unless there are none.
    frames = [f for f in frames if not _is_library(f.filename)] or frames
    frames = frames[-_LOGGED_FRAMES:]
    where = " <- ".join(
        f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(frames)
    )
    return f"{type(exc).__name__}, sqlstate={getattr(cause, 'pgcode', None)}, at {where}"


_LOGGED_FRAMES = 6
_LIBRARY_PATHS = tuple(
    # A set on purpose: stdlib/platstdlib and purelib/platlib often coincide.
    {  # NOSONAR
        os.path.realpath(sysconfig.get_path(name)) + os.sep
        for name in ("stdlib", "platstdlib", "purelib", "platlib")
    }
)


def _is_library(filename: str) -> bool:
    return os.path.realpath(filename).startswith(_LIBRARY_PATHS)


def _loggable_id(value: Any) -> str:
    """The id, unless it contains an e-mail address."""
    value = "" if value is None else str(value)
    return "<redacted>" if "@" in value else value


def _normalise_changes(changes: Mapping[str, Any] | None, action: str) -> dict:
    """Keep only ``before`` and ``after``; the read API returns nothing else.

    A side whose value is ``None`` is dropped: that is how a caller says the
    value could not be read (a failed ``best_effort`` snapshot), and storing
    ``null`` would read as "the value was unset".
    """
    changes = dict(changes or {})
    extra = sorted(set(changes) - {"before", "after"})
    if extra:
        logger.warning(
            "Platform audit: %r changes keys %s ignored; use before/after", action, extra
        )
    return {
        side: changes[side]
        for side in ("before", "after")
        if changes.get(side) is not None
    }


def _resolve_actor(*, request: Any, actor: User | None) -> dict[str, Any]:
    user = actor
    if user is None and request is not None:
        user = getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    key = getattr(request, "platform_api_key", None) if request is not None else None

    if key is not None:
        return {
            "actor": user,
            "actor_type": ActorType.API_KEY,
            "actor_email": _clip((getattr(user, "email", "") or "").lower(), 254),
            "actor_name": _clip(key.name, 255),
            "actor_key_id": str(key.id),
            "actor_key_name": _clip(key.name, 255),
        }
    if user is None:
        return {"actor": None, "actor_type": ActorType.SYSTEM}
    actor_type = (
        ActorType.API_KEY
        if getattr(user, "is_service_account", False)
        else ActorType.USER
    )
    return {
        "actor": user,
        "actor_type": actor_type,
        "actor_email": _clip((user.email or "").lower(), 254),
        "actor_name": _clip(user.get_full_name() or "", 255),
    }


def _request_id(request: Any) -> str:
    value = getattr(request, "id", None) if request is not None else None
    return str(value or getattr(request_id_local, "request_id", "") or "")


def _clip(value: Any, limit: int) -> str:
    return ("" if value is None else str(value))[:limit]


def record_key_update(
    *,
    target_type: str,
    key: Any,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    request: Any,
) -> None:
    """Record a key edit: ``key.enabled``/``key.disabled`` for an ``is_active``
    flip, and ``key.changed`` for any other field that changed.

    ``before`` is ``None`` when it could not be read: what changed is then
    unknown. An ``is_active`` the request set is filed as
    ``key.enabled``/``key.disabled``, so filtering by those actions finds it.
    If the request set any other field, ``key.changed`` records the current
    values of every audited field except ``is_active`` (a snapshot, not a
    diff). With no ``after`` there is nothing to describe. Because this branch
    gates on what the request sent, a field the server changes on its own (a
    global key's ``api_deployments`` cleared for an allow-all key) goes
    unrecorded on a flip-only request whose ``before`` could not be read.
    """
    from platform_audit.actions import Action

    if after is None:
        logger.error("Platform audit: key %s update not recorded, no after", key.id)
        return
    if before is None:
        sent = set(getattr(request, "data", None) or {})
        snapshot = {k: v for k, v in after.items() if k != "is_active"}
        if "is_active" in sent:
            is_active = after.get("is_active")
            record_platform_event(
                action=Action.KEY_ENABLED if is_active else Action.KEY_DISABLED,
                target_type=target_type,
                target_id=key.id,
                target_name=key.name,
                changes={"after": {"is_active": is_active}},
                summary=BEFORE_UNAVAILABLE,
                request=request,
            )
        if snapshot and sent - {"is_active"}:
            record_platform_event(
                action=Action.KEY_CHANGED,
                target_type=target_type,
                target_id=key.id,
                target_name=key.name,
                changes={"after": snapshot},
                summary=f"current values {BEFORE_UNAVAILABLE}",
                request=request,
            )
        return
    changes = diff(before, after)
    flipped = "is_active" in changes["after"]
    if flipped:
        record_platform_event(
            action=Action.KEY_ENABLED if after["is_active"] else Action.KEY_DISABLED,
            target_type=target_type,
            target_id=key.id,
            target_name=key.name,
            changes={
                "before": {"is_active": before.get("is_active")},
                "after": {"is_active": after["is_active"]},
            },
            request=request,
        )
    other = {k: v for k, v in changes["after"].items() if k != "is_active"}
    if other:
        record_platform_event(
            action=Action.KEY_CHANGED,
            target_type=target_type,
            target_id=key.id,
            target_name=key.name,
            changes={
                "before": {k: changes["before"][k] for k in other},
                "after": other,
            },
            summary="changed " + ", ".join(sorted(other)),
            request=request,
        )
