"""Best-effort terminal-ERROR marking for stranded PG-path executions.

Any PG failure that tears down its own recovery handle — the barrier abort
deletes ``pg_barrier_state``; the consumer poison-drop deletes the queue
message — must first make the workflow execution terminal, or the execution is
stranded ``EXECUTING`` forever with nothing left for the reaper to find (the
reaper only recovers executions that still have a barrier row).

:func:`mark_execution_error` centralises that mark: set the execution ERROR via
the internal API, cascading to its non-terminal file executions in the same
backend transaction (so the execution never goes ERROR while its files stay
EXECUTING). It is deliberately best-effort and returns a bool so the caller can
decide what to do on failure (leave the barrier row / re-park the message)
rather than erase the only recovery handle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from unstract.core.data_models import ExecutionStatus

if TYPE_CHECKING:
    from shared.api import InternalAPIClient

logger = logging.getLogger(__name__)


def mark_execution_error(
    api_client: InternalAPIClient,
    execution_id: str,
    organization_id: str,
    *,
    error_message: str,
) -> bool:
    """Mark ``execution_id`` ERROR (+cascade non-terminal files); return success.

    Returns ``True`` iff the backend confirmed the write. NEVER raises: any
    failure — a raised exception, or a ``success=False`` response (the internal
    client reports some write failures that way rather than raising, mirroring
    the reaper / read path) — is logged and returns ``False`` so the caller keeps
    the recovery handle instead of erasing it.

    ``cascade_terminal_files=True`` marks the execution's non-terminal file
    executions to ERROR atomically with the execution, so the two can't drift.

    The reaper keeps its own raise-on-failure variant (``_mark_stranded_error``):
    its delete-guard needs the exception to refuse the barrier-row DELETE, whereas
    the callers here branch on the returned bool.
    """
    try:
        response = api_client.update_workflow_execution_status(
            execution_id=execution_id,
            status=ExecutionStatus.ERROR.value,
            error_message=error_message,
            organization_id=organization_id,
            cascade_terminal_files=True,
        )
    except Exception:
        logger.exception(
            "Failed to mark execution %s ERROR (internal API raised) — leaving the "
            "recovery handle in place for the reaper.",
            execution_id,
        )
        return False
    # ``success`` absent → assume the raised-on-failure legacy contract (True).
    if not getattr(response, "success", True):
        logger.error(
            "Marking execution %s ERROR reported success=False — leaving the "
            "recovery handle in place for the reaper.",
            execution_id,
        )
        return False
    logger.error(
        "Marked stranded execution %s ERROR (+cascade files): %s",
        execution_id,
        error_message,
    )
    return True
