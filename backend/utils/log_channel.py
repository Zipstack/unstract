"""The channel that carries a browser session's live logs and events.

The channel names the Socket.IO room a session's sockets join, the event the
frontend listens for (``logs:<channel>``), and the Redis keys of the session's
UI logs. It travels widely: in API responses (``log_events_id``), on workflow
executions (``execution_log_id``), in worker payloads and in log lines.

It is therefore derived from the session key, never the key itself. The session
key is the value of the HttpOnly session cookie, so anything that exposed it
would hand over the session. The derivation is one-way and keyed with
SECRET_KEY, so a channel id reveals nothing about the session it belongs to.
Both ends compute it from the session key alone: the auth middleware for the
request's work, the socket server from the cookie on connect.
"""

from django.utils.crypto import salted_hmac

# Scopes the HMAC to this use, so the value is never equal to an HMAC that
# Django or another feature computes over the same session key.
_SALT = "unstract.log_channel_id"


def log_channel_id(session_key: str | None) -> str | None:
    """The opaque log channel id of a session, or None without a session."""
    if not session_key:
        return None
    return salted_hmac(_SALT, session_key, algorithm="sha256").hexdigest()
