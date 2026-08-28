"""Result payload for a completed agent-kv job (spec §7.2/§7.3).

Single source of truth for "is this job's result actually available", shared
by ``JobResultView`` (``execution_views.py``) and ``SubmitView``'s
synchronous-wait branch (Task 8, lazily imported to avoid a circular import
at module load time).

Whether the job has even reached COMPLETED is a status-specific concern that
belongs to each caller (``JobResultView`` needs a 409 with a raw
``{"status": ...}`` body for that case; ``SubmitView``'s wait loop needs a
plain 200 for any terminal status). This function only answers "is there
actually a result to hand back for a completed job" — equally true whether
the job never completed at all (no ``result_ref`` was ever written) or it
completed but the result has since expired/been swept.
"""

from django.utils import timezone

from agent_kv.exceptions import JobNotFound
from agent_kv.storage import read_result


def result_payload(job) -> dict:
    """Return the stored engine result for ``job``, unchanged.

    Raises ``JobNotFound`` (404) if the result has expired or its files
    were already swept (blank ``result_ref``) -- including jobs that never
    completed, since those never had a ``result_ref`` to begin with.
    """
    if not job.result_ref or (job.expires_at and job.expires_at < timezone.now()):
        raise JobNotFound()
    return read_result(job.result_ref)
