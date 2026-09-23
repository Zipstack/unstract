"""Shared fakes for executor request-reply dispatch tests.

Several operation suites (summarize, table extract, agentic, …) assert the same
two things about a tool dispatch: *which queue it lands on* and *what payload it
carries*. They used to do that against the SDK's Celery ``ExecutionDispatcher``,
mocking ``celery_app.send_task``. That dispatcher was deleted with the rest of
the Celery transport (UN-4078); the surviving path is
:class:`~unstract.workflow_execution.executor_rpc.PgExecutionDispatcher`, which
enqueues through an injected :class:`QueueTransport` instead.

This module is the single home for the fake transport those suites now share, so
the retarget did not scatter ten near-identical mock classes across the tree.
``test_executor_rpc.py`` keeps its own local ``_FakeTransport`` — it exercises
failure modes (enqueue raising, poll raising, malformed rows) that the operation
suites have no use for, and widening this one to cover them would couple the
happy-path callers to that detail.
"""

from __future__ import annotations

from typing import Any

# ``QUEUE_PREFIX`` is the queue-per-executor prefix. Named ``celery_executor_*``
# for historical reasons and NOT dead Celery surface: ``worker-pg-executor``
# subscribes to exactly these strings (chart ``workerPgExecutor``), so the names
# are live wire contract. Imported from the production constant rather than
# re-declared, so a rename cannot silently pass these tests while stranding the
# real consumer.
from unstract.workflow_execution.executor_rpc import (
    QUEUE_PREFIX,
    ExecResultRow,
    queue_for_executor,
)

__all__ = [
    "QUEUE_PREFIX",
    "EagerExecutorTransport",
    "FakeExecutorTransport",
    "callback_signature",
    "queue_for",
]


def queue_for(executor_name: str) -> str:
    """The queue an executor's dispatches land on.

    Delegates to the production helper rather than re-deriving the rule, so an
    assertion here observes what the dispatcher actually does: a change to the
    naming fails these suites instead of them agreeing with a stale copy.
    """
    return queue_for_executor(executor_name)


def callback_signature(task_name: str, *, queue: str = "celery_callback") -> Any:
    """A real ``Signature`` shaped the way PG self-chaining requires.

    ``signature_to_continuation`` rejects a signature with no task name, no
    queue, or any positional args. A bare ``MagicMock`` fails all three — every
    attribute it auto-creates is truthy, so it trips the positional-args guard —
    which makes it useless as a stand-in here. Imported by the suites that assert
    on the continuation payload so they cannot drift on that shape.
    """
    from celery.canvas import Signature

    return Signature(task_name, args=(), kwargs={}, queue=queue)


class FakeExecutorTransport:
    """Records ``enqueue`` calls and replays a canned result to the poll.

    Exercises :class:`PgExecutionDispatcher` end-to-end with no database. The
    recorded ``enqueue_calls`` are plain kwarg dicts — assert on
    ``calls[0]["queue"]`` / ``["context"]`` / ``["org_id"]`` the way the old
    suites asserted on ``send_task.call_args``.
    """

    def __init__(self, *, result: dict[str, Any] | None = None) -> None:
        self.enqueue_calls: list[dict[str, Any]] = []
        self.wait_timeouts: list[float] = []
        self._result = result

    def enqueue(
        self,
        *,
        queue: str,
        context: Any,
        org_id: str,
        reply_key: str | None = None,
        on_success: Any | None = None,
        on_error: Any | None = None,
        task_id: str | None = None,
    ) -> None:
        # Mirrors the QueueTransport protocol exactly (keyword-only, fixed key
        # set) rather than swallowing **kwargs: a production signature change
        # then fails these suites instead of being silently absorbed.
        self.enqueue_calls.append(
            {
                "queue": queue,
                "context": context,
                "org_id": org_id,
                "reply_key": reply_key,
                "on_success": on_success,
                "on_error": on_error,
                "task_id": task_id,
            }
        )

    def wait_for_result(self, reply_key: str, timeout: float) -> ExecResultRow | None:
        del reply_key
        self.wait_timeouts.append(timeout)
        if self._result is None:
            return None
        return ExecResultRow(status="completed", result=self._result, error="")

    # -- convenience accessors, so callers don't index into the list inline ----

    @property
    def only_call(self) -> dict[str, Any]:
        """The single recorded enqueue; fails loudly if there wasn't exactly one."""
        assert len(self.enqueue_calls) == 1, (
            f"expected exactly one enqueue, got {len(self.enqueue_calls)}"
        )
        return self.enqueue_calls[0]

    @property
    def queue(self) -> str:
        """Queue of the single recorded enqueue."""
        return self.only_call["queue"]

    @property
    def context(self) -> Any:
        """``ExecutionContext`` of the single recorded enqueue."""
        return self.only_call["context"]


class EagerExecutorTransport(FakeExecutorTransport):
    """Runs the ``execute_extraction`` task in-process instead of enqueueing it.

    The full-chain contract test needs dispatcher → task → orchestrator → result to
    actually execute. On the Celery transport that was done by patching
    ``send_task`` to call ``task.apply()``; the equivalent here is a transport whose
    ``enqueue`` runs the task synchronously and hands the outcome back through
    ``wait_for_result``, so the same chain is exercised through the surviving
    dispatcher.

    ``args=[context.to_dict()]`` mirrors :class:`PgClientQueueTransport.enqueue`
    exactly — if the real payload shape changes, this fake must change with it or
    the chain it claims to cover is not the one that ships.
    """

    def __init__(self, task: Any) -> None:
        super().__init__()
        self._task = task

    def enqueue(self, *, context: Any, **kwargs: Any) -> None:
        # ``context`` is named so this fake breaks loudly if the protocol drops
        # it; the rest is forwarded to the base recorder, which pins the full
        # keyword-only key set.
        super().enqueue(context=context, **kwargs)
        outcome = self._task.apply(args=[context.to_dict()])
        self._result = outcome.get()
