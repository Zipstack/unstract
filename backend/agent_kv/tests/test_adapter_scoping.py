"""The adapter lookup must work with NO request-local organization context.

This is the test whose absence let a P1 through. `_resolved_adapters` was
written with `AdapterInstance.objects`, by analogy to the `organization_id`
filter in `_get_job` -- but the two models have different default managers:

* `AgentKVJob` uses `BaseModelManager`, which does not auto-filter, so its
  explicit `organization_id=` is the only filter.
* `AdapterInstance` sets `AdapterInstanceModelManager`, which inherits
  `DefaultOrganizationManagerMixin.get_queryset()` and filters EVERY query by
  `UserContext.get_organization()` -- a request-local thread-local set by the
  tenant middleware.

`/agent-kv/` is deliberately whitelisted past that middleware (the org comes
from the Bearer key, not the URL), so the thread-local is unset and the ambient
filter became `organization=None`. Every valid submit was refused with "no such
adapter in this organization".

Every test in `test_submit_view.py` mocked the lookup, so none of them could
see it. These run against the real manager with the real thread-local unset --
which is the only arrangement that reproduces the production path.

DB-backed, so `TestCase` and the integration tier (`backend/conftest.py`
auto-marks on that basis; no manual marker).
"""

import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.test import TestCase  # noqa: E402

from account_v2.models import Organization  # noqa: E402
from adapter_processor_v2.models import AdapterInstance  # noqa: E402
from rest_framework.exceptions import ValidationError  # noqa: E402

from agent_kv.execution_views import (  # noqa: E402
    _lookup_adapter,
    _resolved_adapters,
)
from utils.user_context import UserContext  # noqa: E402


class TestAdapterLookupWithoutRequestContext(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        self.other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        self.adapter = AdapterInstance.objects.create(
            adapter_name="acme-llm",
            adapter_id="anthropic|abc",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
        )
        # The state the whitelisted route actually runs in: no tenant
        # middleware has run, so there is no ambient organization.
        UserContext.set_organization_identifier(None)

    def test_the_lookup_finds_the_org_s_own_adapter_with_no_user_context(self):
        """The regression. Through `.objects` this returned None and the submit
        was a 400 -- for a correctly-configured caller naming their own adapter.
        """
        self.assertIsNone(
            UserContext.get_organization(),
            "precondition: this route has no ambient organization",
        )

        found = _lookup_adapter(self.adapter.id, self.org.id)

        self.assertIsNotNone(
            found,
            "the caller's own adapter must resolve without a request-local "
            "organization; `.objects` filters by one and returns nothing here",
        )
        self.assertEqual(found.id, self.adapter.id)
        self.assertEqual(found.adapter_type, "LLM")

    def test_the_org_filter_still_excludes_another_org_s_adapter(self):
        """Bypassing the AMBIENT filter must not bypass the explicit one.

        `_base_manager` is unfiltered, so the `organization_id` argument is the
        only tenant boundary left -- if it stopped working, the fix for the
        regression above would have opened the cross-tenant hole it exists to
        close.
        """
        self.assertIsNone(_lookup_adapter(self.adapter.id, self.other.id))

    def test_an_unknown_id_resolves_to_none(self):
        self.assertIsNone(_lookup_adapter(uuid.uuid4(), self.org.id))

    def test_the_ambient_manager_really_does_hide_it(self):
        """Pins the cause, so the comment on `_lookup_adapter` stays truthful.

        If `AdapterInstance.objects` ever stops auto-filtering by the
        thread-local, this fails and `_base_manager` is no longer necessary --
        at which point the explanation should be revisited rather than left
        asserting something that is no longer true.
        """
        via_objects = AdapterInstance.objects.filter(
            id=self.adapter.id, organization_id=self.org.id
        ).first()

        self.assertIsNone(
            via_objects,
            "`.objects` is expected to hide the adapter here -- that is the "
            "whole reason `_lookup_adapter` uses `_base_manager`",
        )


class TestResolvedAdaptersAgainstRealRows(TestCase):
    """`_resolved_adapters` end-to-end against the database, not against mocks.

    `test_submit_view.py` patches `ev._lookup_adapter`, so every property the
    gate reads off an adapter -- `adapter_type`, `is_usable`, `is_available` --
    is only ever compared to a value the stand-in chose for itself. That is
    enough to test the gate's branching and nothing about whether the branches
    match the real columns. These rows get their flags from the model's own
    defaults.

    It is also the only place the refusal-oracle property can honestly be
    tested: "not yours" and "no such adapter" have to come from two GENUINELY
    different database states, which a single mocked lookup cannot produce.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        self.other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        self.key = mock.Mock(organization_id=self.org.id)
        UserContext.set_organization_identifier(None)

    def _adapter(self, *, org=None, adapter_type="LLM", **kwargs):
        return AdapterInstance.objects.create(
            adapter_name=f"a-{uuid.uuid4().hex[:8]}",
            adapter_id="anthropic|abc",
            adapter_type=adapter_type,
            adapter_metadata={},
            organization=org or self.org,
            **kwargs,
        )

    def _entry(self, **roles):
        return {"name": "table", "adapters": {r: str(v) for r, v in roles.items()}}

    def _full_entry(self, **overrides):
        roles = {
            "llm": self._adapter().id,
            "lite_llm": self._adapter().id,
            "x2text": self._adapter(adapter_type="X2TEXT").id,
        }
        roles.update(overrides)
        return self._entry(**roles)

    def test_a_fully_valid_set_of_the_org_s_own_adapters_resolves(self):
        """The happy path, with every flag coming from the DB's own defaults.

        `is_usable` and `is_available` both default True at the model, so this
        also pins that the two new refusals do not reject ordinary adapters
        nobody has touched.
        """
        entry = self._full_entry()

        self.assertEqual(_resolved_adapters(entry, self.key), entry["adapters"])

    def test_a_wrong_type_is_refused_against_a_real_row(self):
        """An X2TEXT id in the `llm` slot.

        Previously asserted only against a mock that was told to report
        `adapter_type="X2TEXT"`; this reads the real column, so the comparison
        against `AdapterTypes.LLM.value` is pinned to the value the DB stores.
        """
        entry = self._full_entry(llm=self._adapter(adapter_type="X2TEXT").id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("expected 'LLM'", str(caught.exception))

    def test_an_exhausted_trial_adapter_is_refused(self):
        """A1. `is_usable=False` is how billing cuts off a frictionless trial.

        The platform service returns the credentials regardless, so this gate
        is the only thing that stops an operator-funded extraction here.
        """
        entry = self._full_entry(llm=self._adapter(is_usable=False).id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("exhausted", str(caught.exception))

    def test_a_deprecated_adapter_is_refused(self):
        entry = self._full_entry(llm=self._adapter(is_available=False).id)

        with self.assertRaises(ValidationError) as caught:
            _resolved_adapters(entry, self.key)

        self.assertIn("deprecated", str(caught.exception))

    def test_another_org_s_adapter_and_a_nonexistent_one_refuse_identically(self):
        """The oracle property, from two genuinely different DB states.

        If these two messages ever diverge, `POST /agent-kv/` becomes an oracle
        for which adapter UUIDs are real in OTHER organizations: a caller
        brute-forcing ids learns "exists but not yours" from "does not exist".

        The mocked version of this test could not fail -- one patched lookup
        returns None for both cases, so it compared one branch's message to
        itself. Here one id is a real row owned by `self.other` and the other
        is a UUID no row has.
        """
        foreign = self._adapter(org=self.other).id
        nowhere = uuid.uuid4()

        messages = []
        for adapter_id in (foreign, nowhere):
            with self.assertRaises(ValidationError) as caught:
                _resolved_adapters(self._full_entry(llm=adapter_id), self.key)
            messages.append(str(caught.exception))

        self.assertEqual(
            messages[0],
            messages[1],
            "a foreign adapter and a nonexistent one must be indistinguishable; "
            f"got {messages[0]!r} vs {messages[1]!r}",
        )

    def test_no_adapters_requested_is_a_no_op(self):
        """The `kv` shape: env-configured extractors send `{}` and must pass."""
        self.assertEqual(_resolved_adapters({"name": "kv", "adapters": {}}, self.key), {})


class TestTheJobRowRecordsWhatItSpent(TestCase):
    """The adapters a run was dispatched with must be recoverable AFTERWARDS.

    Adapter choice is per-request, caller-controlled and cost-bearing on the
    `table` path. Before the `adapters` column the chosen ids reached
    `executor_params` and nothing else -- not the job row, not the status
    document, not `usage_summary` -- so "which model did job X use?", the first
    question in any billing dispute, needed a `usage_v2` join on `run_id` that
    the API cannot perform and the customer cannot see.

    DB-backed because the point is that the value SURVIVES the request.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        from agent_kv.models import AgentKVJob, JobExtractor

        job = AgentKVJob(
            organization_id=self.org.id,
            extractor=JobExtractor.TABLE,
            **kwargs,
        )
        job.save()
        return job

    def test_the_adapters_round_trip_through_the_database(self):
        adapters = {
            "llm": str(uuid.uuid4()),
            "lite_llm": str(uuid.uuid4()),
            "x2text": str(uuid.uuid4()),
        }

        job = self._job(adapters=adapters)
        job.refresh_from_db()

        assert job.adapters == adapters

    def test_the_status_document_reports_them(self):
        from agent_kv.execution_views import _status_document

        adapters = {"llm": str(uuid.uuid4())}
        doc = _status_document(self._job(adapters=adapters))

        assert doc["adapters"] == adapters, doc

    def test_a_job_with_no_adapters_reports_an_empty_dict_not_null(self):
        """`kv` is env-configured and names none, and rows predating the column
        genuinely ran on operator credentials -- `{}` is the honest value for
        both, and a stable type is easier for a client than `null | object`.
        """
        from agent_kv.execution_views import _status_document

        job = self._job()

        assert job.adapters == {}
        assert _status_document(job)["adapters"] == {}

    def test_no_adapter_metadata_is_ever_stored_on_the_job(self):
        """The column is returned to the caller, so it must carry ids only.

        `AdapterInstance.adapter_metadata` holds the PROVIDER CREDENTIALS. A
        future change that widened this field to "the adapter" rather than "its
        id" would publish those to whoever submitted the job.
        """
        adapters = {"llm": str(uuid.uuid4()), "x2text": str(uuid.uuid4())}
        job = self._job(adapters=adapters)
        job.refresh_from_db()

        for role, value in job.adapters.items():
            assert isinstance(value, str), (role, value)
            # A bare UUID string, not a serialized adapter.
            uuid.UUID(value)


class TestNeverDispatchedAgainstRealRows(TestCase):
    """`_never_dispatched` against the database, because mocks hid it twice.

    Round-2 C1 was "it read the stale in-memory row". The first fix for that
    dropped the `status == PENDING` arm and lost a second case: a job RUNNING
    with `dispatched_at` still NULL, which happens whenever post-enqueue
    bookkeeping fails (`dispatch_job` deliberately swallows that -- the task is
    already queued, so a failure there must not be reported as a failed
    dispatch).

    Both fixes were written against patched managers, which is why neither
    caught the other. These use real rows.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        from agent_kv.models import AgentKVJob, JobExtractor

        job = AgentKVJob(
            organization_id=self.org.id, extractor=JobExtractor.TABLE, **kwargs
        )
        job.save()
        return job

    def test_a_pristine_pending_job_has_no_executor(self):
        """The one case the slot release exists for."""
        from agent_kv.execution_views import _never_dispatched
        from agent_kv.models import JobStatus

        job = self._job(status=JobStatus.PENDING)

        assert _never_dispatched(job) is True

    def test_a_dispatched_job_has_an_executor(self):
        from agent_kv.execution_views import _never_dispatched
        from agent_kv.models import JobStatus
        from django.utils import timezone

        job = self._job(status=JobStatus.DISPATCHED, dispatched_at=timezone.now())

        assert _never_dispatched(job) is False

    def test_a_job_with_a_reported_stage_has_an_executor_even_with_no_dispatched_at(
        self,
    ):
        """The hole the first fix opened.

        `dispatched_at` NULL and a stage recorded: bookkeeping failed, the
        executor ran anyway and reported progress. Releasing here hands a live
        executor's slot to the next submit.
        """
        from agent_kv.execution_views import _never_dispatched
        from agent_kv.models import JobStatus

        job = self._job(
            status=JobStatus.RUNNING,
            dispatched_at=None,
            stage="table_extraction",
            stages={"table_extraction": {"status": "running"}},
        )

        assert _never_dispatched(job) is False, (
            "a RUNNING job with a reported stage has a live executor; its slot "
            "belongs to the finalize callback"
        )

    def test_the_cancel_rewriting_status_does_not_resurrect_the_release(self):
        """Why `status` is not one of the markers.

        By the time this runs the cancel has already written CANCELLED, so a
        status-based test could only be answered from the stale object. The two
        durable markers must still say "executor exists".
        """
        from agent_kv.execution_views import _never_dispatched
        from agent_kv.models import JobStatus

        job = self._job(
            status=JobStatus.CANCELLED, dispatched_at=None, stage="table_extraction"
        )

        assert _never_dispatched(job) is False

    def test_a_stale_in_memory_row_cannot_override_the_database(self):
        """The original C1 interleaving, end to end.

        The in-memory object is doctored to look pristine -- exactly what the
        cancel path holds, having fetched it before `mark_terminal` -- while the
        row in the database carries the dispatch.
        """
        from agent_kv.execution_views import _never_dispatched
        from agent_kv.models import AgentKVJob, JobStatus
        from django.utils import timezone

        job = self._job(status=JobStatus.PENDING)
        AgentKVJob.objects.filter(id=job.id).update(
            status=JobStatus.DISPATCHED, dispatched_at=timezone.now()
        )

        # The snapshot the cancel path is holding.
        job.status = JobStatus.PENDING
        job.dispatched_at = None

        assert _never_dispatched(job) is False


class TestACancelThatLostTheRaceKeepsItsResult(TestCase):
    """A cancel landing after extraction finished must not destroy the answer.

    The window is real and the money is already gone when it opens: the engine
    flushes OCR and LLM usage before the executor's final stage report, so by
    the time a cancel can collide with that report the customer has been
    billed. `FinalizeView` then wrote the result, `mark_terminal` correctly
    declined to restatus a terminal row, and the file was DELETED -- so
    `GET result` returned `{"success": false, "status": "cancelled"}` with no
    sign that a paid-for result had existed.

    DB-backed because the whole mechanism is a guarded UPDATE racing another
    guarded UPDATE; a mock would just agree with whichever one I wrote.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        from agent_kv.models import AgentKVJob, JobExtractor

        # `input_ref` defaults to a live staged input: a cancelled job keeps
        # its input until TTL, and a BLANK one is the purge marker the salvage
        # must refuse (see `test_a_purged_job_does_not_get_its_result_back`).
        kwargs.setdefault("input_ref", "org/o/agent_kv/j/input.pdf")
        job = AgentKVJob(
            organization_id=self.org.id, extractor=JobExtractor.TABLE, **kwargs
        )
        job.save()
        return job

    def test_the_result_is_attached_to_a_cancelled_job(self):
        from agent_kv.models import AgentKVJob, JobStatus

        job = self._job(status=JobStatus.CANCELLED)

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="r/1.json", usage_summary={"pages": 3}
        )
        job.refresh_from_db()

        assert attached is True
        assert job.result_ref == "r/1.json"
        assert job.usage_summary == {"pages": 3}

    def test_it_never_changes_status_or_completed_at(self):
        """The cancel stays won, and stays visible.

        If this ever starts flipping `status`, a cancelled job would read as
        completed and the guard `mark_terminal` exists to enforce would have
        been bypassed by the back door.
        """
        from agent_kv.models import AgentKVJob, JobStatus
        from django.utils import timezone

        stamped = timezone.now()
        job = self._job(status=JobStatus.CANCELLED, completed_at=stamped)

        AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="r/2.json"
        )
        job.refresh_from_db()

        assert job.status == JobStatus.CANCELLED
        assert job.completed_at == stamped

    def test_a_completed_or_failed_job_is_left_alone(self):
        """Scoped to CANCELLED on purpose.

        A COMPLETED or FAILED row already has its own outcome; grafting a late
        callback's result onto it would overwrite a real one (COMPLETED) or
        invent one for a run that failed.
        """
        from agent_kv.models import AgentKVJob, JobStatus

        for status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job = self._job(status=status)
            attached = AgentKVJob.attach_result_to_cancelled(
                job.id, self.org.id, result_ref="r/nope.json"
            )
            job.refresh_from_db()
            assert attached is False, status
            assert job.result_ref == "", status

    def test_a_second_callback_does_not_overwrite_the_first(self):
        """At-least-once delivery means this runs twice.

        The second call must report False so its caller deletes its own freshly
        written file rather than orphaning it -- `result_ref=""` in the filter
        is what makes that happen.
        """
        from agent_kv.models import AgentKVJob, JobStatus

        job = self._job(status=JobStatus.CANCELLED)

        first = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="r/first.json"
        )
        second = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="r/second.json"
        )
        job.refresh_from_db()

        assert (first, second) == (True, False)
        assert job.result_ref == "r/first.json"

    def test_a_blank_ref_is_refused_so_the_caller_keeps_its_delete(self):
        from agent_kv.models import AgentKVJob, JobStatus

        job = self._job(status=JobStatus.CANCELLED)

        assert (
            AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref="")
            is False
        )

    def test_another_org_cannot_attach_a_result(self):
        from agent_kv.models import AgentKVJob, JobStatus

        other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        job = self._job(status=JobStatus.CANCELLED)

        assert (
            AgentKVJob.attach_result_to_cancelled(
                job.id, other.id, result_ref="r/x.json"
            )
            is False
        )

    def test_the_result_payload_serves_it_while_still_reporting_cancelled(self):
        """The read half. `status` must stay `cancelled` -- the cancel WAS
        honoured and a client has to be able to see that -- while `success` is
        True because there is a real, paid-for result to hand over.
        """
        from agent_kv.execution_views_result import result_payload
        from agent_kv.models import JobStatus
        from unittest import mock

        job = self._job(status=JobStatus.CANCELLED, result_ref="r/3.json")

        with mock.patch(
            "agent_kv.execution_views_result.read_result",
            return_value={"tables": [], "row_count": 0},
        ):
            payload = result_payload(job)

        assert payload["status"] == "cancelled"
        assert payload["success"] is True
        assert payload["extractors"]["table"] == {"tables": [], "row_count": 0}

    def test_an_ordinary_cancel_is_byte_identical_to_before(self):
        """The common path -- cancelled mid-run, nothing computed -- must not
        change shape just because the salvage path exists.
        """
        from agent_kv.execution_views_result import result_payload
        from agent_kv.models import JobStatus

        job = self._job(status=JobStatus.CANCELLED)

        assert result_payload(job) == {"success": False, "status": "cancelled"}


class TestThePurgeGuardOnTheSalvage(TestCase):
    """A result the caller DELETEd must not come back.

    `result_ref=""` alone cannot distinguish "cancelled, nothing stored yet"
    from "cancelled and explicitly purged": `JobDeleteView` deletes the files
    and blanks BOTH refs, which is exactly the row the salvage filter matched.
    A late finalize would then re-attach a newly written result to a job whose
    data the caller asked to have destroyed.

    `input_ref` is the discriminator: a cancelled job keeps its staged input
    (only a WINNING finalize drops it, and the salvage path is by definition a
    losing one), while DELETE and TTL cleanup both blank it.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _cancelled(self, **kwargs):
        from agent_kv.models import AgentKVJob, JobExtractor, JobStatus

        job = AgentKVJob(
            organization_id=self.org.id,
            extractor=JobExtractor.TABLE,
            status=JobStatus.CANCELLED,
            **kwargs,
        )
        job.save()
        return job

    def test_a_purged_job_does_not_get_its_result_back(self):
        """The deletion violation. Both refs blank = the caller purged it."""
        from agent_kv.models import AgentKVJob

        job = self._cancelled(input_ref="", result_ref="")

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="org/o/agent_kv/j/result.json"
        )
        job.refresh_from_db()

        assert attached is False, (
            "re-attached a result to a job the caller DELETEd; purged data "
            "must not become readable again"
        )
        assert job.result_ref == ""

    def test_a_live_cancelled_job_still_gets_its_result(self):
        """The other half: the guard must not refuse the case it exists for."""
        from agent_kv.models import AgentKVJob

        job = self._cancelled(input_ref="org/o/agent_kv/j/input.pdf", result_ref="")

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="org/o/agent_kv/j/result.json"
        )
        job.refresh_from_db()

        assert attached is True
        assert job.result_ref == "org/o/agent_kv/j/result.json"

    def test_a_ttl_swept_job_does_not_get_a_result_grafted_on(self):
        """TTL cleanup blanks both refs, same shape as DELETE.

        Re-attaching there would put a result on a job past its retention
        window, which `JobResultView`'s expiry gate would then 404 anyway --
        but the file would exist, unreferenced-but-reachable, after the
        retention window the customer was promised.
        """
        from agent_kv.models import AgentKVJob
        from django.utils import timezone
        from datetime import timedelta

        job = self._cancelled(
            input_ref="",
            result_ref="",
            expires_at=timezone.now() - timedelta(days=1),
        )

        assert (
            AgentKVJob.attach_result_to_cancelled(
                job.id, self.org.id, result_ref="org/o/agent_kv/j/late.json"
            )
            is False
        )
