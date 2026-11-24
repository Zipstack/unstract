"""Pushing a completed job's extraction into a named human-review queue.

**The seam, not the queue.** The queue itself is `manual_review_v2`, a cloud
pluggable app that is absent from an OSS deployment entirely -- same situation
as the extraction engine, which this module deliberately mirrors: probe, call
if present, degrade cleanly if not. Nothing here knows how a queue is stored.

**Why this is a push and not a wait.** The job completes normally and its
result is served by `GET /{job_id}/result` exactly as it always was; a copy
goes to the queue for a human. That is the shape the API-deployment feature
this mirrors already has -- its docs say the call "returns immediately" and the
reviewed data is fetched later from the approved-results endpoint, keyed on the
queue name. Two consequences worth stating, because the alternative design was
considered and rejected:

* No new job state. A job parked in `RUNNING` awaiting a human would be
  force-failed as `"Job timed out"` by the sweep after
  `AGENT_KV_STUCK_JOB_GRACE_SECONDS` (6 hours), and would hold its
  concurrency slot the whole time -- so five pending reviews would exhaust an
  organisation's `AGENT_KV_CONCURRENT_LIMIT` and block the API outright.
* No change to the result contract. `success`, `status` and `extractors` mean
  what they meant before; `hitl_queue_name` is echoed so a caller can find the
  review copy.

**Failing to push does NOT fail the job.** The extraction is done, stored and
billed by the time this runs. Losing a review copy is bad and is logged at
ERROR with the queue name so it can be requeued by hand; turning it into a job
failure would discard a paid-for result to report a secondary problem, and the
caller would get `success: false` for a result that exists.
"""

from __future__ import annotations

import logging
import os

from django.conf import settings

from agent_kv.constants import HITL_QUEUE_TYPE_API
from agent_kv.models import AgentKVJob

logger = logging.getLogger(__name__)

#: One log line per process for an absent plugin, not one per job. A deployment
#: without the review app pushes nothing for every job it runs, and an
#: unguarded message there is an ERROR per request straight into Sentry --
#: exactly the fault `_CAPS_LOGGED` in `tasks.py` and `_EXTRACTOR_LOGGED` in
#: `execution_serializers.py` were added for.
_MISSING_LOGGED: set[str] = set()


def _review_plugin():
    """The review app's push entry point, or ``None`` where it is not deployed.

    A dynamic import rather than a module-level one: this module is imported by
    the internal API on every finalize, and a hard import would make the whole
    OSS backend depend on a cloud app. `manual_review_v2`'s own README names
    dynamic imports as how it is reached for this reason.
    """
    try:
        from pluggable_apps.manual_review_v2 import agentic_extract_push
    except ImportError:
        return None
    return agentic_extract_push


def _document_name(job) -> str:
    """A name for the staged document, since the caller's own is not kept.

    `stage_input` writes `{...}/{job_id}/input{ext}`, discarding the uploaded
    name, so the extension is the only part of it that survives.
    """
    ext = os.path.splitext(job.input_ref or "")[1]
    return f"{job.id}{ext}"


def push_completed_job(job, result: dict | None) -> bool:
    """Push ``job``'s extraction to the queue it named. Returns whether it went.

    Called once per job, by the finalize request that WON the terminal guard --
    `FinalizeView._complete` only reports `finalized` to that one request, so a
    duplicate or retried finalize cannot enqueue a second review copy.

    `result` is the extraction as the caller would read it. It is passed in
    rather than re-read from storage because the finalize path already holds
    it, and a second read could race the TTL cleanup that may purge it.
    """
    queue = (job.hitl_queue_name or "").strip()
    if not queue:
        return False

    if not settings.AGENT_KV_HITL_ENABLED:
        # Reachable only if the flag was turned off between submit and
        # finalize: the submit serializer refuses the field outright while it
        # is off. Worth a line rather than a silent drop, because the caller
        # was promised a review by a 202 that validated.
        logger.warning(
            "agentic-extract: job %s named review queue %r but HITL is disabled; "
            "no review record was created",
            job.id,
            queue,
        )
        return False

    plugin = _review_plugin()
    if plugin is None:
        if "missing" not in _MISSING_LOGGED:
            _MISSING_LOGGED.add("missing")
            logger.error(
                "agentic-extract: review queue %r was requested but the manual "
                "review app is not installed on this deployment. Submits are "
                "gated on AGENT_KV_HITL_ENABLED, so this is a misconfiguration: "
                "the flag is on and the app is absent. Logged once per process.",
                queue,
            )
        return False

    try:
        pushed = plugin.enqueue_api_record(
            organization_id=job.organization.organization_id,
            hitl_queue_name=queue,
            # The approved-results reader REQUIRES `file` and `status`, and
            # rejects the record after it has already dequeued it -- on Postgres
            # that is an unrecoverable loss. Only this side can supply them.
            #
            # The caller's own filename is not available: `stage_input` writes
            # `input{ext}` and keeps no record of it. The job id carries the
            # real extension instead, so a reviewer gets something that
            # identifies the document and the caller gets something they can
            # match to their own job.
            document_name=_document_name(job),
            job_status=(job.status or "").lower(),
            queue_type=HITL_QUEUE_TYPE_API,
            source_id=str(job.id),
            document_data=result or {},
            metadata={
                "source": "agentic-extract",
                "extractor": job.extractor,
                # The caller's own data, so a reviewer sees the context the
                # extraction was requested with.
                "custom_data": job.custom_data or {},
                "tags": job.tags or [],
            },
        )
    except Exception:
        # Never fails the job -- see the module docstring. The queue name is in
        # the message because it is what a requeue needs.
        logger.exception(
            "agentic-extract: failed to push job %s to review queue %r; the "
            "extraction itself is stored and served normally",
            job.id,
            queue,
        )
        return False

    # A narrow UPDATE rather than `job.save()`: the finalize path has already
    # written this row through `mark_terminal` and holds a stale in-memory copy,
    # so a full save would write every other field back from it.
    #
    # Guarded separately because NOTHING here may escape. The caller queues the
    # terminal webhook and drops the staged input only after this returns
    # (`internal_views.FinalizeView.post`), and a retried finalize reports
    # `finalized: False`, so an exception raised here loses the customer's
    # webhook permanently rather than merely losing the read-back coordinate.
    queue_class = (pushed or {}).get("queue_class") or ""
    if queue_class:
        try:
            AgentKVJob.objects.filter(id=job.id).update(hitl_queue_class=queue_class)
            job.hitl_queue_class = queue_class
        except Exception:
            logger.exception(
                "agentic-extract: job %s was pushed to review queue %r but its "
                "queue class could not be recorded; the review copy exists and "
                "the caller must look it up by queue name",
                job.id,
                queue,
            )

    logger.info("agentic-extract: job %s pushed to review queue %r", job.id, queue)
    return True
