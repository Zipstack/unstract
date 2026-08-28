"""Thin scheduler-side tasks for the Agent-KV maintenance periodics (spec §5.4).

Mirrors ``dashboard_metrics_tasks.py``'s shape and role in this worker (UN-3796):
these do **no** work themselves, each just calls a backend internal endpoint that
does the real work, because the workers image has no Django and the ORM-heavy
job-row work (terminalizing stuck/never-dispatched jobs, deleting staged files)
can only run there.

Unlike the dashboard-metrics proxies, the calls here go through the shared
``InternalAPIClient`` facade (``shared.api.InternalAPIClient``) rather than a
bespoke ``httpx`` client -- ``agent_kv_finalize`` already lives on that facade
(Task 11) for the Agent-KV terminal callbacks
(``ide_callback/agent_kv_tasks.py::_get_api_client``), and the sweep/TTL-cleanup
calls added here (``agent_kv_sweep``/``agent_kv_ttl_cleanup``,
``workers/shared/api/internal_client.py``) are its siblings on the same client,
not a second HTTP stack for the same feature.

Two internal endpoints, both platform-wide (no ``org_id``, spec §5.4):

- ``POST /internal/v1/agent-kv/sweep/`` -- terminalizes never-dispatched
  ``PENDING`` jobs and stuck ``DISPATCHED``/``RUNNING`` jobs.
- ``POST /internal/v1/agent-kv/ttl-cleanup/`` -- deletes staged input/result
  files for jobs past ``expires_at`` and blanks their refs.

Both handlers are idempotent and batch-capped server-side
(``backend/agent_kv/internal_views.py``), so redelivery/backlog from a missed
tick is safe without extra guards here -- exactly like the dashboard-metrics
proxies' own redelivery story.

**Not registered under a dotted Beat-mirroring name for a Beat row that
exists** (contrast ``dashboard_metrics_tasks.py``, whose names are pinned to
verbatim Beat rows it mirrors): there is no pre-existing Beat/PG-scheduler
entry for these two tasks to match, since Agent-KV shipped with the internal
endpoints but no periodic registration (spec §5.4, this feature's own
deploy-checklist gap). The ``agent_kv.sweep``/``agent_kv.ttl_cleanup`` wire
names below are this task pair's own new contract -- an operator registers a
``PgPeriodicTask`` row against them (see `docs/agent-kv-api.md`'s deploy
checklist for the exact shape), the same PG-scheduler mechanism the
dashboard-metrics periodics use.
"""

import logging
from typing import Any

from queue_backend import worker_task

logger = logging.getLogger(__name__)


def _get_api_client():
    """Lazily build an InternalAPIClient.

    Mirrors ``ide_callback.agent_kv_tasks._get_api_client``'s lazy import +
    plain instantiation (no shared config/session) for the same reason: keeps
    this module import-cycle-free at load time.
    """
    from shared.api import InternalAPIClient

    return InternalAPIClient()


@worker_task(name="agent_kv.sweep")
def agent_kv_sweep() -> dict[str, Any]:
    """Terminalize never-dispatched PENDING and stuck Agent-KV jobs (spec §5.4)."""
    return _get_api_client().agent_kv_sweep()


@worker_task(name="agent_kv.ttl_cleanup")
def agent_kv_ttl_cleanup() -> dict[str, Any]:
    """Delete staged Agent-KV input/result files past their TTL (spec §5.4)."""
    return _get_api_client().agent_kv_ttl_cleanup()
