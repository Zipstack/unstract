"""Abandoning an in-flight call when the caller no longer wants its result.

Some calls this SDK makes cannot be interrupted from outside: a synchronous
``litellm.completion`` parks its thread on a socket read, and no timeout,
signal or flag reaches it. When a user stops a Prompt Studio run, waiting for
that call to return can mean holding a worker for minutes on work nobody wants.

This module supplies the missing lever. A caller passes an **abort predicate**
— a plain ``() -> bool`` — and the SDK stops waiting when it turns True. The
SDK never learns *why*: the predicate is a closure the caller owns, so nothing
here knows about Prompt Studio, Redis, or how a stop is signalled. That keeps
the workflow and API-deployment paths, which share this SDK and have no stop
button, entirely unaffected — they simply pass no predicate.

Two ways to supply it:

* explicitly, as a ``should_abort=`` argument; or
* ambiently, via :func:`abort_scope`, which sets a :class:`~contextvars.ContextVar`
  that adapters read *at call time*. The ambient route exists because adapters
  are often constructed deep inside plugin code the caller cannot reach, and
  because one long-lived client may serve several units of work that need
  narrowing one at a time.

Aborting is best effort and never fatal: a predicate that raises is read as
False, so a failure to determine intent lets the work proceed rather than
killing something healthy.

**What an abort does not do.** Closing our end of a request does not stop the
provider processing it, and does not reliably avoid being billed for it. What
it buys is the worker and the user getting on with their lives.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import threading
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from typing import Any, Final, TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "AbortCheck",
    "AbortedError",
    "abort_scope",
    "current_abort_check",
    "run_abortable",
    "should_abort_now",
    "sliced_sleep",
]

T = TypeVar("T")

#: A caller-supplied predicate: True means "stop waiting for this work".
AbortCheck = Callable[[], bool]


class AbortedError(Exception):
    """Raised when a call was abandoned because the caller asked to stop.

    Deliberately NOT a subclass of ``TimeoutError`` or any transport error:
    the retry machinery classifies those as transient and would dutifully
    retry the very call we just walked away from.
    """


# How long to wait between checks of the predicate while blocked on a call.
# Half a second is imperceptible to a user pressing Stop, and the predicate is
# expected to be cheap (callers memoize a negative result).
_DEFAULT_POLL_SECONDS: Final = 0.5

# After cancelling, how long to let the coroutine unwind before we stop caring.
# The task is cancelled either way; this only bounds how long we wait to watch
# it happen, so a provider client with a slow teardown cannot hold us up.
_DEFAULT_GRACE_SECONDS: Final = 5.0


# --------------------------------------------------------------------------
# Ambient predicate
# --------------------------------------------------------------------------

_abort_check_var: contextvars.ContextVar[AbortCheck | None] = contextvars.ContextVar(
    "unstract_abort_check", default=None
)


@contextmanager
def abort_scope(check: AbortCheck | None) -> Iterator[None]:
    """Make *check* the ambient abort predicate for the duration of the block.

    Passing ``None`` is meaningful and supported: it scopes a region as
    non-abortable, which is what a caller with no stop button does.
    """
    token = _abort_check_var.set(check)
    try:
        yield
    finally:
        _abort_check_var.reset(token)


def current_abort_check() -> AbortCheck | None:
    """The ambient abort predicate, or ``None`` outside any scope."""
    return _abort_check_var.get()


def should_abort_now(check: AbortCheck | None = None) -> bool:
    """Evaluate *check* (or the ambient one) without ever raising.

    A predicate that blows up must not take the caller's work with it, so a
    failure is logged once and read as "do not abort".
    """
    predicate = check if check is not None else current_abort_check()
    if predicate is None:
        return False
    try:
        return bool(predicate())
    except Exception:
        logger.warning(
            "Abort predicate raised; treating as 'do not abort'", exc_info=True
        )
        return False


def sliced_sleep(
    seconds: float,
    should_abort: AbortCheck | None = None,
    *,
    slice_seconds: float = _DEFAULT_POLL_SECONDS,
) -> None:
    """Sleep, but wake early if the caller stops wanting the result.

    A bare ``time.sleep`` in a retry backoff is itself uninterruptible, so a
    stop can sit inside one for as long as the backoff runs — up to a minute
    with the usual exponential settings. Slicing it keeps the response to a
    stop bounded by *slice_seconds* instead.

    Raises:
        AbortedError: If the predicate turns True before the sleep completes.
    """
    import time  # local: keeps the module import-light for callers that only type-check

    if seconds <= 0:
        return
    predicate = should_abort if should_abort is not None else current_abort_check()
    if predicate is None:
        time.sleep(seconds)
        return

    deadline = time.monotonic() + seconds
    while True:
        if should_abort_now(predicate):
            raise AbortedError("Aborted while waiting to retry")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(slice_seconds, remaining))


async def asliced_sleep(
    seconds: float,
    should_abort: AbortCheck | None = None,
    *,
    slice_seconds: float = _DEFAULT_POLL_SECONDS,
) -> None:
    """Async twin of :func:`sliced_sleep`, for the coroutine retry path."""
    if seconds <= 0:
        return
    predicate = should_abort if should_abort is not None else current_abort_check()
    if predicate is None:
        await asyncio.sleep(seconds)
        return

    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while True:
        if should_abort_now(predicate):
            raise AbortedError("Aborted while waiting to retry")
        remaining = deadline - loop.time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(slice_seconds, remaining))


# --------------------------------------------------------------------------
# The shared event loop
# --------------------------------------------------------------------------
#
# Why one loop for the whole process, rather than asyncio.run() per call:
# litellm caches its async HTTP clients in a module-level dict keyed by
# provider (``litellm.in_memory_llm_clients_cache``). A cached client holds a
# reference to the loop it was built on, so once that loop is closed every
# later call through the same client fails with "Event loop is closed". One
# long-lived loop sidesteps the whole problem.
#
# The loop is started lazily — a process that never aborts anything never pays
# for a thread — and re-created after a fork, because the consumer forks its
# children (workers/pg_queue_consumer/supervisor.py) and threads do not
# survive that.

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _reset_after_fork() -> None:
    """Forget the parent's loop: its thread does not exist in this child."""
    global _loop, _loop_thread
    _loop = None
    _loop_thread = None


if hasattr(os, "register_at_fork"):  # pragma: no cover - platform dependent
    os.register_at_fork(after_in_child=_reset_after_fork)


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return the process-wide background loop, starting it on first use."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is not None and _loop_thread is not None and _loop_thread.is_alive():
            return _loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=loop.run_forever,
            name="unstract-abortable-calls",
            daemon=True,
        )
        thread.start()
        _loop, _loop_thread = loop, thread
        logger.debug("Started the abortable-call event loop")
        return loop


def run_abortable(
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    should_abort: AbortCheck | None = None,
    *,
    poll: float = _DEFAULT_POLL_SECONDS,
    grace: float = _DEFAULT_GRACE_SECONDS,
) -> T:
    """Run a coroutine on the shared loop, abandoning it if the caller stops.

    The calling (synchronous) thread blocks in *poll*-second slices, checking
    the predicate between them. When it turns True the underlying task is
    cancelled — which closes the in-flight HTTP request — and this raises
    rather than returning a result nobody wants.

    With no predicate this is simply "run this coroutine and wait", which is
    why the caller can pass one unconditionally.

    Raises:
        AbortedError: If the predicate turned True. Raised even if the
            cancelled coroutine takes longer than *grace* to unwind, since
            waiting on a slow teardown would defeat the purpose.
    """
    import concurrent.futures

    predicate = should_abort if should_abort is not None else current_abort_check()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        # Already inside a loop: submitting to another and blocking here would
        # deadlock that loop. The caller gets the un-abortable path instead,
        # which is correct-but-slower rather than broken.
        raise RuntimeError(
            "run_abortable cannot be called from a thread with a running event loop"
        )

    future = asyncio.run_coroutine_threadsafe(coro_factory(), _get_loop())
    while True:
        try:
            return future.result(timeout=poll)
        except concurrent.futures.TimeoutError:
            if not should_abort_now(predicate):
                continue
            future.cancel()
            try:
                future.exception(timeout=grace)
            except (concurrent.futures.TimeoutError, concurrent.futures.CancelledError):
                # Either it is still unwinding, or it unwound as cancelled.
                # Both mean the same thing to us: stop waiting.
                pass
            except Exception:
                # The call failed on its way out. The abort is what the caller
                # asked for and is the more useful signal, so it wins.
                logger.debug("Aborted call also raised while unwinding", exc_info=True)
            raise AbortedError(
                "Call abandoned because the caller asked to stop"
            ) from None
        except concurrent.futures.CancelledError as exc:
            raise AbortedError("Call was cancelled") from exc
