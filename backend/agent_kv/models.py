import uuid

from account_v2.models import User
from django.db import models
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
