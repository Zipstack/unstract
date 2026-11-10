"""Records where a user is signed in, and ends those sessions on request.

A `SessionRecord` is written at sign-in (`user_logged_in`, which every
distribution's authentication plugin reaches through `django.contrib.auth.login`)
and refreshed from `CustomAuthMiddleware` on session-authenticated requests.
That middleware is referenced by every distribution's settings, which is why the
refresh lives there rather than in a middleware of its own.
"""

import contextlib
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from functools import cache, partial
from importlib import import_module
from typing import Any

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache as django_cache
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from logs_helper.log_service import LogService

from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.constants import ROW_BACKED_SESSION_ENGINES
from account_v2.models import SessionRecord, User
from account_v2.serializer import SignedInSessionSerializer

logger = logging.getLogger(__name__)

# The spec caps activity writes at one per session per minute.
ACTIVITY_REFRESH_INTERVAL = timedelta(minutes=1)
_TOUCH_CACHE_PREFIX = "session_record_touch:"
# How often any request may run the platform-wide idle sweep. Sign-in alone is
# not enough: with no sign-ins, dead records would keep their IPs indefinitely.
IDLE_SWEEP_INTERVAL = timedelta(hours=1)
_IDLE_SWEEP_CACHE_KEY = "session_record_idle_sweep"

# First match wins. Chromium-based browsers also send "Chrome/" and "Safari/",
# and Chrome sends "Safari/", so those come first; Safari itself is told apart by
# its "Version/" token.
_BROWSERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/")),
    ("Opera", re.compile(r"\b(?:OPR|Opera)/")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/")),
    # Safari puts "Version/x" just before "Safari/", with "Mobile/x" between on iOS.
    ("Safari", re.compile(r"\bVersion/\S+ (?:Mobile/\S+ )?Safari/")),
)
# iOS before macOS (iPad UAs mention "Mac OS X"); Android before Linux.
_OPERATING_SYSTEMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Windows", re.compile(r"\bWindows NT\b")),
    ("iOS", re.compile(r"\b(?:iPhone|iPad|iPod)\b")),
    ("Android", re.compile(r"\bAndroid\b")),
    ("ChromeOS", re.compile(r"\bCrOS\b")),
    ("macOS", re.compile(r"\b(?:Macintosh|Mac OS X)\b")),
    ("Linux", re.compile(r"\bLinux\b")),
)


@dataclass(frozen=True)
class DeviceInfo:
    browser: str | None
    os: str | None

    @property
    def label(self) -> str | None:
        if self.browser and self.os:
            return f"{self.browser} on {self.os}"
        return self.browser or self.os


def parse_user_agent(user_agent: str) -> DeviceInfo:
    """Browser and OS from a user agent; None for anything not recognised."""

    def first_match(table: tuple[tuple[str, re.Pattern[str]], ...]) -> str | None:
        return next((name for name, pattern in table if pattern.search(user_agent)), None)

    return DeviceInfo(browser=first_match(_BROWSERS), os=first_match(_OPERATING_SYSTEMS))


@cache
def _location_resolver() -> Callable[[str], str | None] | None:
    dotted_path = getattr(settings, "SESSION_LOCATION_RESOLVER", None)
    return import_string(dotted_path) if dotted_path else None


def _resolve_location(ip_address: str | None) -> str | None:
    if not ip_address:
        return None
    try:
        resolver = _location_resolver()
        if resolver is None:
            return None
        return resolver(ip_address)
    except Exception:
        # A location is decoration; a resolver that fails to import or to run
        # must not stop the session from being recorded.
        logger.warning("Session location resolver failed", exc_info=True)
        return None


def _client_ip(request: HttpRequest) -> str | None:
    # REMOTE_ADDR only, for the reason given in `custom_auth_middleware._client_ip`:
    # nothing here validates a forwarding chain, so X-Forwarded-For is untrusted.
    return request.META.get("REMOTE_ADDR") or None


class IdentityProviderError(Exception):
    """The identity provider failed while ending a session."""


def _session_store_class() -> type:
    return import_module(settings.SESSION_ENGINE).SessionStore


def _auth_service() -> Any:
    if AuthenticationPluginRegistry.is_plugin_available():
        return AuthenticationPluginRegistry.get_plugin()
    from account_v2.authentication_service import AuthenticationService

    return AuthenticationService()


_LOCATION_MAX_LENGTH = SessionRecord._meta.get_field("location").max_length


def _session_details(request: HttpRequest) -> dict[str, Any]:
    """What a record stores about the browser, resolved before any transaction
    opens so a slow location resolver never holds one.
    """
    ip_address = _client_ip(request)
    location = _resolve_location(ip_address) or ""
    return {
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        "ip_address": ip_address,
        "location": location[:_LOCATION_MAX_LENGTH],
    }


def _sessions_have_rows() -> bool:
    return settings.SESSION_ENGINE in ROW_BACKED_SESSION_ENGINES


def _session_row_exists(session_key: str) -> bool:
    return Session.objects.filter(session_key=session_key).exists()


def _replace_with_empty_session(request: HttpRequest) -> None:
    """Start the response from an empty session, so it clears the cookie.

    For a session whose row is already gone but whose store failed part-way:
    left in place, the store would try to save itself back over the deleted row.
    """
    http_request = getattr(request, "_request", request)
    http_request.session = _session_store_class()()


def _disconnect_session_sockets(session_key: str) -> None:
    """Disconnect an ended session's sockets.

    Sockets are authenticated only when they connect, so without this a socket
    of a revoked session keeps receiving events, in the per-user room too, until
    it disconnects. Best effort: the session is already over.
    """
    try:
        from utils.log_events import disconnect_session_sockets

        disconnect_session_sockets(session_key)
    except Exception:
        logger.warning("Failed to disconnect sockets of an ended session", exc_info=True)


def _renew_session_sockets(session_key: str) -> None:
    try:
        from utils.log_events import renew_session_sockets

        # A refresh interval past the session's own lifetime: the session can be
        # saved (and extended) up to one interval after the last refresh.
        renew_session_sockets(
            session_key,
            ttl=settings.SESSION_COOKIE_AGE
            + int(ACTIVITY_REFRESH_INTERVAL.total_seconds()),
        )
    except Exception:
        logger.warning("Failed to renew socket tracking of a session", exc_info=True)


def _close_socket_room(room: str) -> None:
    try:
        from utils.log_events import sio

        sio.close_room(room)
    except Exception:
        logger.warning("Failed to close a socket room", exc_info=True)


def _close_refresh_window(session_key: str) -> None:
    """Send the session's next request to touch()'s row check.

    A cached copy that outlives the ended session can still authenticate, and an
    open refresh window would admit it without that check.
    """
    with contextlib.suppress(Exception):
        django_cache.delete(f"{_TOUCH_CACHE_PREFIX}{session_key}")


class SessionTracker:
    @staticmethod
    def _upsert(request: HttpRequest, user: User, details: dict[str, Any]) -> None:
        SessionRecord.objects.update_or_create(
            session_key=request.session.session_key,
            defaults={**details, "user": user, "last_active_at": timezone.now()},
        )

    @classmethod
    def record_sign_in(cls, request: HttpRequest, user: User) -> None:
        # `login()` flushes rather than cycles the session when a different user
        # was signed in on this browser, which leaves no key until the response
        # saves it. Saving now gives the record a key; the later save reuses it.
        if request.session.session_key is None:
            request.session.save()
        # Kept out of the upsert's transaction: a failing platform-wide sweep
        # must not lose this user's own record.
        try:
            cls._sweep_idle_if_due()
        except Exception:
            logger.warning("Failed to sweep idle session records", exc_info=True)
        details = _session_details(request)
        with transaction.atomic():
            # The signing-in user's own records are checked exactly.
            cls.live_records(user)
            cls._upsert(request, user, details)

    @classmethod
    def _sweep_idle_if_due(cls) -> None:
        if django_cache.add(
            _IDLE_SWEEP_CACHE_KEY,
            True,
            timeout=int(IDLE_SWEEP_INTERVAL.total_seconds()),
        ):
            # Its own savepoint: callers swallow a failure, and under
            # ATOMIC_REQUESTS a database error outside one would leave the
            # request's transaction unusable.
            with transaction.atomic():
                cls._sweep_idle()

    @staticmethod
    def _sweep_idle() -> None:
        # Records keep an IP address, so a dead one is removed within one session
        # lifetime (plus at most one sweep interval) of its last use, even for a
        # user who never lists their sessions again. A live session is touched on
        # every authenticated request, so a record idle for longer than a session
        # can live is dead: that bound keeps the global sweep on an index instead
        # of an anti-join against every live session.
        idle_cutoff = timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE)
        SessionRecord.objects.filter(last_active_at__lt=idle_cutoff).delete()

    @classmethod
    def touch(cls, request: HttpRequest) -> bool:
        """Refresh last-active for a session-authenticated request.

        Returns False when the session has already been ended and must be
        refused. The cache-backed engine authenticates from its cached copy, and
        that copy can outlive the session's row: a concurrent request can re-cache
        a session as it is revoked, or deleting the copy can fail after the row
        went. The row is checked whenever the refresh window is closed, and only a
        session whose row exists opens it, so a refused session is refused on
        every request after. Ending a session closes its window too; only a
        request whose row check raced the end can reopen it, for one interval.

        Otherwise best effort: this runs on every authenticated request, so any
        failure is logged and swallowed rather than failing the request.
        """
        session_key = request.session.session_key
        user = request.user
        if not (session_key and user.is_authenticated):
            return True
        touch_key = f"{_TOUCH_CACHE_PREFIX}{session_key}"
        try:
            try:
                window_open = django_cache.get(touch_key) is not None
            except Exception:
                # Unknown is not open: the cached copy of the session may
                # still have loaded, so its row must be checked.
                logger.warning("Could not read the session refresh window", exc_info=True)
                window_open = False
            if window_open:
                return True
            if _sessions_have_rows() and not _session_row_exists(session_key):
                logger.info("Refused an ended session of user %s", user.pk)
                # Refused whether or not the surviving cached copy can be dropped.
                try:
                    # The response clears the cookie.
                    request.session.flush()
                except Exception:
                    logger.warning(
                        "Could not drop the cached copy of an ended session of user %s",
                        user.pk,
                        exc_info=True,
                    )
                    _replace_with_empty_session(request)
                return False
            # Opened only now, past the row check: a window opened by a refused
            # session would let its later requests skip that check.
            if not django_cache.add(
                touch_key,
                True,
                timeout=int(ACTIVITY_REFRESH_INTERVAL.total_seconds()),
            ):
                return True  # A concurrent request is refreshing it.
            with transaction.atomic():
                updated = SessionRecord.objects.filter(
                    session_key=session_key, user=user
                ).update(last_active_at=timezone.now())
            if not updated:
                # Signed in before session recording existed: first seen now.
                details = _session_details(request)
                with transaction.atomic():
                    cls._upsert(request, user, details)
            _renew_session_sockets(session_key)
            cls._sweep_idle_if_due()
        except Exception:
            logger.warning(
                "Failed to refresh session activity for user %s",
                user.pk,
                exc_info=True,
            )
        return True

    @staticmethod
    def forget(session_key: str | None) -> None:
        if session_key:
            SessionRecord.objects.filter(session_key=session_key).delete()

    @staticmethod
    def live_records(user: User) -> list[SessionRecord]:
        """The user's recorded sessions that are still live, pruning the rest.

        Liveness must come from `django_session`, not from the record alone: a
        request that passed authentication just before its session was revoked
        can still `touch()` and recreate the record. Checking the session here is
        what keeps such a record out of the list.
        """
        records = list(SessionRecord.objects.filter(user=user))
        live_keys = set(
            Session.objects.filter(
                session_key__in=[record.session_key for record in records],
                expire_date__gt=timezone.now(),
            ).values_list("session_key", flat=True)
        )
        stale_ids = [r.id for r in records if r.session_key not in live_keys]
        if stale_ids:
            SessionRecord.objects.filter(id__in=stale_ids).delete()
        return [r for r in records if r.session_key in live_keys]

    @staticmethod
    def idp_sessions(request: HttpRequest) -> list[dict[str, Any]]:
        """Sessions the identity provider owns, from the plugin if it lists any.

        A plugin opts in by defining `list_idp_sessions(request)`, returning
        entries shaped like a `users/sessions/` item, and
        `revoke_idp_sessions(request, session_id=None)`, ending one provider
        session or all of them and returning whether it ended anything. Both are
        optional; the basic-auth service defines neither.
        """
        hook = getattr(_auth_service(), "list_idp_sessions", None)
        if hook is None:
            return []
        try:
            entries = list(hook(request))
        except Exception:
            logger.warning(
                "Identity provider session listing failed for user %s",
                request.user.pk,
                exc_info=True,
            )
            return []
        sessions = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                logger.warning(
                    "Dropped a malformed identity provider session: %s",
                    type(entry).__name__,
                )
                continue
            entry = {
                **{key: (None if value == "" else value) for key, value in entry.items()},
                # Only the session making this request is current, and it is ours.
                "is_current": False,
            }
            serializer = SignedInSessionSerializer(data=entry)
            if serializer.is_valid():
                sessions.append(serializer.validated_data)
            else:
                # One bad entry from a plugin must not take the whole list down.
                logger.warning(
                    "Dropped a malformed identity provider session: %s",
                    serializer.errors,
                )
        return sessions

    @staticmethod
    def _revoke_idp(request: HttpRequest, session_id: str | None) -> bool:
        """Whether the provider ended anything.

        Raises `IdentityProviderError` when it fails, so a caller can tell a
        failure from an id the provider does not know.
        """
        hook = getattr(_auth_service(), "revoke_idp_sessions", None)
        if hook is None:
            return False
        try:
            return bool(hook(request, session_id=session_id))
        except Exception as error:
            raise IdentityProviderError from error

    @classmethod
    def _end(cls, request: HttpRequest, session_key: str) -> None:
        """End a session: its row, its cached copy and its record.

        Deleting the row is what ends it. If only the cached copy then fails to
        go, the session is still over: `touch()` refuses a session whose row is
        gone. So that failure is logged rather than raised.
        """
        is_current = session_key == request.session.session_key
        try:
            if is_current:
                # Flushing the live session also makes the response clear the cookie.
                request.session.flush()
            else:
                _session_store_class()(session_key=session_key).delete()
        except Exception:
            if _session_row_exists(session_key):
                raise
            logger.warning(
                "Ended a session of user %s, but its cached copy remains",
                request.user.pk,
                exc_info=True,
            )
            if is_current:
                _replace_with_empty_session(request)
        _close_refresh_window(session_key)
        cls.forget(session_key)

    @classmethod
    def _after_end_on_commit(cls, request: HttpRequest, session_key: str) -> None:
        # Socket cleanup must follow the commit: before it, a reconnecting socket
        # still sees the session's row and the user's old generation, passes, and
        # would join after the cleanup ran. Immediate without a transaction.
        transaction.on_commit(partial(cls._after_end, request, session_key))

    @staticmethod
    def _after_end(request: HttpRequest, session_key: str) -> None:
        # Best effort: the session is already over, and an unreachable cache or
        # broker must not undo or fail that.
        # Again after the commit: a request that saw the row before it went may
        # have reopened the window meanwhile.
        _close_refresh_window(session_key)
        _disconnect_session_sockets(session_key)
        try:
            LogService.remove_logs_on_logout(session_id=session_key)
        except Exception:
            logger.warning(
                "Failed to clear logs of an ended session of user %s",
                request.user.pk,
                exc_info=True,
            )

    @classmethod
    def revoke(cls, request: HttpRequest, session_id: str) -> bool:
        """End one of the caller's sessions. False if it is not theirs or unknown."""
        try:
            record_id = uuid.UUID(session_id)
        except ValueError:
            # Not one of ours; the provider may own it.
            return cls._revoke_idp(request, session_id)
        record = SessionRecord.objects.filter(id=record_id, user=request.user).first()
        if record is None:
            return cls._revoke_idp(request, session_id)
        cls._end(request, record.session_key)
        cls._after_end_on_commit(request, record.session_key)
        logger.info("Signed out one session of user %s", request.user.pk)
        return True

    @classmethod
    def revoke_all(cls, request: HttpRequest) -> None:
        """End every session of the caller, the one making this request last."""
        user = request.user
        current_key = request.session.session_key
        # Ends the sessions with no record too: one signed in before recording
        # existed, or whose recording failed at sign-in, still carries the old
        # generation's auth hash and is refused on its next request.
        User.objects.filter(pk=user.pk).update(
            session_generation=F("session_generation") + 1
        )
        # Every session of the user is refused once this commits, including any
        # with no record (whose sockets cannot be found by session), so empty the
        # per-user room then: a socket that connects earlier is evicted, and one
        # that connects later is refused by the new generation.
        transaction.on_commit(partial(_close_socket_room, f"user:{user.pk}"))
        session_keys = set(
            SessionRecord.objects.filter(user=user).values_list("session_key", flat=True)
        )
        session_keys.discard(current_key)
        ended = []
        for session_key in session_keys:
            # The generation bump has already refused these sessions; ending
            # each one is cleanup, so one failure must not skip the rest or
            # leave the current session (and its cookie) in place.
            try:
                with transaction.atomic():
                    cls._end(request, session_key)
                ended.append(session_key)
            except Exception:
                logger.warning(
                    "Failed to end a revoked session of user %s",
                    user.pk,
                    exc_info=True,
                )
                # Refused by the bump either way, so it must not stay listed.
                with contextlib.suppress(Exception), transaction.atomic():
                    cls.forget(session_key)
        for session_key in ended:
            cls._after_end_on_commit(request, session_key)
        try:
            cls._revoke_idp(request, session_id=None)
        except IdentityProviderError:
            # Our own sessions are already ended; the provider's are best effort.
            logger.warning(
                "Identity provider session revoke failed for user %s",
                user.pk,
                exc_info=True,
            )
        if current_key:
            try:
                # Its own savepoint, like the others: under ATOMIC_REQUESTS a
                # database error outside one would roll back the bump and every
                # deletion above while the response still reports success.
                with transaction.atomic():
                    cls._end(request, current_key)
                ended.append(current_key)
                cls._after_end_on_commit(request, current_key)
            except Exception:
                # Already refused by the bump; report the sign-out as done.
                logger.warning(
                    "Failed to end the current session of user %s",
                    user.pk,
                    exc_info=True,
                )
                _replace_with_empty_session(request)
        logger.info(
            "Signed out every session of user %s (%d ended cleanly)",
            user.pk,
            len(ended),
        )
