"""Records where a user is signed in, and ends those sessions on request.

A `SessionRecord` is written at sign-in (`user_logged_in`, which every
distribution's authentication plugin reaches through `django.contrib.auth.login`)
and refreshed from `CustomAuthMiddleware` on session-authenticated requests.
That middleware is referenced by every distribution's settings, which is why the
refresh lives there rather than in a middleware of its own.
"""

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import cache
from importlib import import_module
from typing import Any

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache as django_cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from logs_helper.log_service import LogService

from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.models import SessionRecord, User

logger = logging.getLogger(__name__)

# The spec caps activity writes at one per session per minute.
ACTIVITY_REFRESH_INTERVAL = timedelta(minutes=1)
_TOUCH_CACHE_PREFIX = "session_record_touch:"

# First match wins, so browsers built on Chromium are listed before Chrome and
# Chrome before Safari (each carries the tokens of the ones after it).
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
    resolver = _location_resolver()
    if resolver is None:
        return None
    try:
        return resolver(ip_address)
    except Exception:
        # A location is decoration; a failing resolver must not block sign-in.
        logger.warning("Session location resolver failed", exc_info=True)
        return None


def _client_ip(request: HttpRequest) -> str | None:
    # REMOTE_ADDR only, for the reason given in `custom_auth_middleware._client_ip`:
    # nothing here validates a forwarding chain, so X-Forwarded-For is untrusted.
    return request.META.get("REMOTE_ADDR") or None


def _session_store_class() -> type:
    return import_module(settings.SESSION_ENGINE).SessionStore


def _auth_service() -> Any:
    if AuthenticationPluginRegistry.is_plugin_available():
        return AuthenticationPluginRegistry.get_plugin()
    from account_v2.authentication_service import AuthenticationService

    return AuthenticationService()


class SessionTracker:
    @staticmethod
    def _upsert(request: HttpRequest, user: User) -> None:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        ip_address = _client_ip(request)
        SessionRecord.objects.update_or_create(
            session_key=request.session.session_key,
            defaults={
                "user": user,
                "user_agent": user_agent,
                "ip_address": ip_address,
                "location": _resolve_location(ip_address) or "",
                "last_active_at": timezone.now(),
            },
        )

    @classmethod
    def record_sign_in(cls, request: HttpRequest, user: User) -> None:
        # `login()` flushes rather than cycles the session when a different user
        # was signed in on this browser, which leaves no key until the response
        # saves it. Saving now gives the record a key; the later save reuses it.
        if request.session.session_key is None:
            request.session.save()
        with transaction.atomic():
            cls._prune_stale(user)
            cls._upsert(request, user)

    @classmethod
    def _prune_stale(cls, user: User) -> None:
        # Records keep a client IP, so they must not outlive their session even
        # for a user who never lists their sessions again. A live session is
        # touched on every authenticated request, so a record idle for longer
        # than a session can live is dead: that bound keeps the global sweep on
        # an index instead of an anti-join against every live session. The
        # signing-in user's own records are checked exactly.
        idle_cutoff = timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE)
        SessionRecord.objects.filter(last_active_at__lt=idle_cutoff).delete()
        cls.live_records(user)

    @classmethod
    def touch(cls, request: HttpRequest) -> None:
        """Refresh last-active for a session-authenticated request.

        Best effort: this runs on every authenticated request, so any failure is
        logged and swallowed rather than failing the request it rides on.
        """
        session_key = request.session.session_key
        user = request.user
        if not (session_key and user.is_authenticated):
            return
        try:
            if not django_cache.add(
                f"{_TOUCH_CACHE_PREFIX}{session_key}",
                True,
                timeout=int(ACTIVITY_REFRESH_INTERVAL.total_seconds()),
            ):
                return
            updated = SessionRecord.objects.filter(
                session_key=session_key, user=user
            ).update(last_active_at=timezone.now())
            if not updated:
                # Signed in before session recording existed: first seen now.
                with transaction.atomic():
                    cls._upsert(request, user)
        except IntegrityError:
            # A concurrent request recorded the same session first.
            pass
        except Exception:
            logger.warning("Failed to refresh session activity", exc_info=True)

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
            return list(hook(request))
        except Exception:
            logger.warning("Identity provider session listing failed", exc_info=True)
            return []

    @staticmethod
    def _revoke_idp(request: HttpRequest, session_id: str | None) -> bool:
        hook = getattr(_auth_service(), "revoke_idp_sessions", None)
        if hook is None:
            return False
        try:
            return bool(hook(request, session_id=session_id))
        except Exception:
            # Our own sessions are already ended; the provider's are best effort.
            logger.warning("Identity provider session revoke failed", exc_info=True)
            return False

    @classmethod
    def _end(cls, request: HttpRequest, session_key: str) -> None:
        LogService.remove_logs_on_logout(session_id=session_key)
        if session_key == request.session.session_key:
            # Flushing the live session also makes the response clear the cookie.
            request.session.flush()
        else:
            _session_store_class()(session_key=session_key).delete()
        cls.forget(session_key)

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
        session_keys = set(
            SessionRecord.objects.filter(user=user).values_list("session_key", flat=True)
        )
        session_keys.discard(current_key)
        for session_key in session_keys:
            cls._end(request, session_key)
        cls._revoke_idp(request, session_id=None)
        if current_key:
            cls._end(request, current_key)
