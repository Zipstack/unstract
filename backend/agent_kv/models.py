import uuid

from account_v2.models import User
from django.db import models, transaction
from django.utils import timezone
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin

from agent_kv.constants import TABLE_EXTRACTOR_NAME, V1_EXTRACTOR_NAME


class AgentKVKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=512, blank=True, default="")
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="agent_kv_keys_created",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    class Meta:
        db_table = "agent_kv_key"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_agent_kv_key_name_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"


class JobStatus(models.TextChoices):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobExtractor(models.TextChoices):
    """The extractor names a job row may record.

    `status` has had `choices` since 0001 and `extractor` was the one
    stringly-typed field without them -- so nothing but a reader's memory
    connected the column to `EXTRACTOR_ROUTES`.

    KV is listed even though this deployment refuses it: the column records
    which extractor RAN, and rows written before the carve-out legitimately
    say `kv`. Routability is `EXTRACTOR_ROUTES`' job, and these two sets are
    deliberately not the same thing -- see `test_table_extractor_routing.py`.
    """

    KV = V1_EXTRACTOR_NAME
    TABLE = TABLE_EXTRACTOR_NAME


class AgentKVJob(DefaultOrganizationMixin, BaseModel):
    TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(
        AgentKVKey,
        on_delete=models.SET_NULL,
        null=True,
        related_name="jobs",
    )
    task_id = models.UUIDField(null=True, blank=True)
    # Which extractor this job ran. v1 dispatches exactly one per job, but
    # WHICH one is now a choice, and status/result key their payloads by it --
    # without this column a table job's output would be filed under `kv`.
    #
    # NO DEFAULT, deliberately. Migration 0002 added this column with
    # `default="kv"`, which was the historical truth at the time (the API
    # accepted exactly one extractor and it was always `kv`) and is now a
    # trap: a creation path that omits `extractor=` files a TABLE job as
    # `kv`, and `kv` is a valid key in `STAGE_NAMES_BY_EXTRACTOR`, so
    # `_status_document` hands back the KV stage list and silently drops
    # `table_extraction` from every status response. The job runs, the caller
    # is billed, and the stages array is empty with no warning logged --
    # because nothing is wrong as far as the filter can tell.
    #
    # With no default, an omission is loud instead: `""` matches no route, so
    # `dispatch_job` raises and the job terminalizes as FAILED with an error
    # the caller can see, and `_status_document` logs the unknown-extractor
    # warning. Which extractor ran is a fact about the job, not something with
    # a sensible default.
    extractor = models.CharField(max_length=32, choices=JobExtractor.choices)
    status = models.CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    stage = models.CharField(max_length=32, blank=True, default="")
    stages = models.JSONField(default=dict, blank=True)
    pages_total = models.IntegerField(null=True, blank=True)
    #: Which platform adapters this run was dispatched with, by role --
    #: ``{"llm": "<uuid>", "lite_llm": "<uuid>", "x2text": "<uuid>"}``.
    #:
    #: Recorded because adapter choice is now a per-request, caller-controlled,
    #: COST-BEARING decision (the `table` extractor runs on the submitter's own
    #: adapters, not operator env credentials). Without it the ids reached
    #: `executor_params` and nothing else: neither the status document nor
    #: `usage_summary` reported them, so "which model did job X use?" -- the
    #: first question in any billing dispute -- could only be answered by
    #: joining `usage_v2` on `run_id`, which the API cannot do and a customer
    #: cannot see at all.
    #:
    #: Empty for an env-configured extractor (`kv`), which is why it is a dict
    #: with a `{}` default rather than three nullable columns: the two
    #: credential models coexist, one per extractor.
    #:
    #: Ids only. Deliberately never `adapter_metadata` -- that is where the
    #: provider credentials live, and this column is returned to the caller.
    adapters = models.JSONField(default=dict, blank=True)
    input_ref = models.CharField(max_length=512, blank=True, default="")
    result_ref = models.CharField(max_length=512, blank=True, default="")
    usage_summary = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # When TTL cleanup last failed to delete one of this job's files. NULL means
    # "never attempted, or last attempt succeeded", and it is what separates
    # the two lanes run_ttl_cleanup processes: NOT NULL rows are retries, which
    # get a reserved slice of each batch, and NULL rows are new expirations,
    # which get the rest. Capping both is what stops either side starving the
    # other. See run_ttl_cleanup.
    cleanup_failed_at = models.DateTimeField(null=True, blank=True)
    # Set once this job's stored files have been destroyed on purpose: by an
    # explicit `DELETE /agent-kv/{job_id}` or by the TTL sweep. One-way, and
    # written UNCONDITIONALLY by both of those paths -- before the deletes are
    # attempted, and regardless of whether any individual delete succeeded.
    #
    # It exists because purge state CANNOT be inferred from `input_ref` /
    # `result_ref`, and three reverted attempts to do so are the evidence. Those
    # two columns carry three different meanings at once:
    #
    #   * blank  -- nothing was ever staged/produced, or
    #   * blank  -- it was staged/produced and then purged, or
    #   * SET    -- it was purged but the object delete FAILED, so the ref is
    #              deliberately kept as the handle `run_ttl_cleanup` retries
    #              from (see `storage.delete_job_files`).
    #
    # So neither "the ref is blank" nor "the ref is set" tells you whether the
    # caller asked for this job's data to be destroyed. This column does, and
    # it is the only thing that does.
    #
    # Two readers depend on that:
    #
    #   * `attach_result_to_cancelled` refuses to attach a late result to a
    #     purged job -- otherwise data the caller DELETEd becomes readable again.
    #   * `JobResultView` refuses to SERVE a purged job's result even when a ref
    #     survived a failed delete, which is the case a ref-based check cannot
    #     see at all.
    #
    # Deliberately NOT "the files are gone": a failed delete leaves this True
    # with the object still in the bucket and its ref still set, which is
    # exactly what lets TTL cleanup retry while the API already treats the job
    # as purged. "The caller asked for this to be destroyed" is a fact about the
    # request, so it is recorded as one instead of being re-derived later.
    files_purged = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(null=True, blank=True)
    webhook_url = models.URLField(max_length=1024, blank=True, default="")

    class Meta:
        db_table = "agent_kv_job"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["expires_at"]),
            # Serves BOTH of run_ttl_cleanup's lanes, each of which sorts by a
            # single column ascending behind a predicate on this index's
            # leading column:
            #   retries: WHERE cleanup_failed_at IS NOT NULL ORDER BY cleanup_failed_at
            #   fresh:   WHERE cleanup_failed_at IS NULL     ORDER BY expires_at
            # Deliberately a plain ascending index. The first version of that
            # query asked for `cleanup_failed_at ASC NULLS FIRST`, which a
            # btree index cannot serve (btree is NULLS LAST ascending), so
            # Postgres sorted every matching expired row before applying the
            # 500-row limit -- work that grew with the backlog. Splitting the
            # query removed the NULLS FIRST rather than adding a second index
            # with a non-default null order.
            models.Index(fields=["cleanup_failed_at", "expires_at"]),
        ]

    @classmethod
    def mark_files_purged(cls, job_id, organization_id):
        """Record that this job's files are being destroyed; return the row as
        it is NOW.

        Two jobs in one call, and they have to be one call:

        1. Set ``files_purged`` -- UNCONDITIONALLY, before any delete is
           attempted. It records the caller's intent, not the outcome, so a
           delete that fails must not leave it False (see the field's comment).
        2. Hand back the row read under ``SELECT ... FOR UPDATE``, so the caller
           deletes the files that actually exist rather than the ones its own
           earlier read saw.

        **Why the lock.** ``attach_result_to_cancelled`` can write a
        ``result_ref`` onto a CANCELLED row at any moment. Without serializing
        the two, this interleaving loses:

            purge reads the row        -> result_ref ""
            attach commits             -> result_ref set, file written
            purge sets files_purged
            purge deletes files from its STALE copy -> only the input
            purge blanks the refs it cleared

        which leaves a result file in the bucket that the purge never deleted,
        on a row whose ref it then blanked -- so TTL cleanup (whose candidate
        filter is ``input_ref > "" OR result_ref > ""``) can never reconsider
        it, and extracted customer data outlives its retention window with
        nothing pointing at it. Taking the row lock here, and taking it in
        ``attach_result_to_cancelled`` too, makes the two mutually exclusive:
        either the attach committed BEFORE this read (so its ref is in the row
        returned, and its file is deleted with everything else) or it runs
        after this commit (so it sees ``files_purged=True``, matches nothing,
        and its caller deletes the file it just wrote). There is no third
        interleaving.

        The lock is held only for the marker write -- the object-store deletes
        happen after it is released, on the row returned here. Blocking a
        concurrent attach for one UPDATE is the point; blocking it for the
        duration of a bucket round-trip is not.

        Returns the row, or ``None`` if it no longer exists (job rows are
        retained for the audit trail, so a caller that just read one can treat
        ``None`` as unreachable and fall back to its own copy).
        """
        with transaction.atomic():
            row = (
                cls.objects.select_for_update()
                .filter(id=job_id, organization_id=organization_id)
                .first()
            )
            if row is None:
                return None
            cls.objects.filter(id=job_id, organization_id=organization_id).update(
                files_purged=True
            )
            row.files_purged = True
            return row

    @classmethod
    def attach_result_to_cancelled(
        cls, job_id, organization_id, *, result_ref, usage_summary=None
    ) -> bool:
        """Keep a paid-for result on a job that was CANCELLED mid-flight.

        The race this exists for: extraction completes -- OCR and LLM already
        spent and flushed by the engine -- and only then does the executor's
        final stage report land, by which time a cancel has terminalized the
        row. The executor returns success with the full output, and before this
        it went nowhere: ``FinalizeView.post`` short-circuited on the
        already-terminal row and never wrote it (the ordinary case,
        ``FinalizeView._salvage``), or wrote it and then DELETED it as an orphan
        when ``mark_terminal`` correctly declined to restatus a terminal row
        (the narrow case, ``FinalizeView._complete``). Either way the customer
        was billed for an answer that was destroyed, with ``GET result``
        reporting only ``{"success": false, "status": "cancelled"}`` and one
        INFO line.

        Deliberately NOT part of ``mark_terminal``, and deliberately unable to
        change ``status`` or ``completed_at``: the cancel stays won and stays
        visible. This adds a pointer to work that was already paid for, nothing
        more -- ``mark_terminal`` remains the only way to reach a terminal
        state. ``result_payload`` then serves the data alongside
        ``status: "cancelled"``.

        The guard is one filtered UPDATE, and every clause in it earns its place:

        * ``status=CANCELLED`` -- a COMPLETED or FAILED row already owns its
          outcome, and grafting a late callback's result onto it would either
          overwrite a real result or invent one for a run that failed.
        * ``result_ref=""`` -- idempotency under at-least-once delivery. A
          second callback matches nothing, returns False, and its caller deletes
          the file IT just wrote instead of orphaning it.
        * ``files_purged=False`` -- the purge guard. A job the caller DELETEd
          (or one the TTL sweep sent through) must never get a result back;
          doing so makes purged customer data readable again. **This cannot be
          expressed with the ref columns** -- that was attempt 1 (``result_ref``
          alone: DELETE blanks the refs and leaves exactly the row the filter
          matched) and attempt 2 (plus ``input_ref > ""``: unsound, because
          ``delete_job_files`` deliberately KEEPS a ref whose delete failed, so
          a non-blank ``input_ref`` does not prove the job was never purged).
          See the ``files_purged`` field comment.

        ``select_for_update`` around it is what stops ``mark_files_purged``
        interleaving between this guard and its write -- the full argument is in
        that method's docstring. Both sides must take the lock for either to be
        safe.

        Returns True when this call attached the result (and the caller must
        therefore keep the file), False when it did not (caller deletes it).
        """
        if not result_ref:
            return False
        fields = {"result_ref": result_ref}
        if usage_summary is not None:
            fields["usage_summary"] = usage_summary
        with transaction.atomic():
            # Locked by identity only; the guard itself lives in the UPDATE
            # below so there is exactly one copy of it, in SQL.
            locked = (
                cls.objects.select_for_update()
                .filter(id=job_id, organization_id=organization_id)
                .first()
            )
            if locked is None:
                return False
            return bool(
                cls.objects.filter(
                    id=job_id,
                    organization_id=organization_id,
                    status=JobStatus.CANCELLED,
                    result_ref="",
                    files_purged=False,
                ).update(**fields)
            )

    @classmethod
    def mark_terminal(
        cls,
        job_id,
        organization_id,
        new_status,
        *,
        error="",
        result_ref="",
        usage_summary=None,
    ) -> bool:
        """The ONLY way to reach a terminal state (spec §5.4 write guard).

        Guarded UPDATE: at-least-once callbacks, cancel, and the sweep can all
        race; whoever lands first wins and everyone else no-ops.

        The `.exclude(status__in=TERMINAL)` below guards the ROW, not the
        argument -- so without the check that opens this method,
        `mark_terminal(..., JobStatus.RUNNING)` would stamp
        `status=RUNNING, completed_at=now()`: a row that reads as finished to
        every TTL/sweep query that keys off `completed_at`, is invisible to
        the terminal guard, and can never be terminalized again by anything
        that trusts `completed_at`. No caller does this today; the method is
        named for the invariant, so it enforces it rather than documenting it.
        """
        if new_status not in cls.TERMINAL:
            raise ValueError(
                f"mark_terminal called with non-terminal status {new_status!r}; "
                f"expected one of {sorted(cls.TERMINAL)}"
            )
        fields = {"status": new_status, "completed_at": timezone.now()}
        if error:
            fields["error"] = error
        if result_ref:
            fields["result_ref"] = result_ref
        if usage_summary is not None:
            fields["usage_summary"] = usage_summary
        updated = (
            cls.objects.filter(id=job_id, organization_id=organization_id)
            .exclude(status__in=list(cls.TERMINAL))
            .update(**fields)
        )
        return updated == 1
