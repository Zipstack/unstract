"""A cancel that lost the race keeps its paid-for result -- and a purge wins.

The defect: the engine flushes OCR and LLM usage BEFORE the executor's final
stage report, so a cancel colliding with that report lands after the customer
has been billed. ``FinalizeView._complete`` then wrote the result,
``mark_terminal`` correctly declined to restatus a terminal row, and the `else`
branch deleted the file -- money taken, answer destroyed, ``GET result``
reporting only ``{"success": false, "status": "cancelled"}``.

The obstacle, which is why this took four attempts: ``JobStatusView.delete``
guaranteed that a purged job could not be resurrected BY RELYING on the late
finalize deleting its own orphaned write. Keeping the result removes exactly
that cleanup, so the guarantee has to be re-established some other way -- and
three attempts to re-establish it from ``input_ref``/``result_ref`` were
reverted, because those columns mean "never set", "purged" and "purge attempted,
delete failed, ref kept for a TTL retry" at different times.

``files_purged`` records the fact instead of inferring it. These tests are
DB-backed on purpose: every mechanism here is a guarded UPDATE racing another
guarded UPDATE, or an ordering between a marker write and a read, and a mock
would only ever agree with whichever one happened to be written. That is how the
previous attempts passed review-less: 34 DB-free tests agreed with a condition
that skipped the re-read on the one path needing it, because their mocked
``mark_terminal`` left the in-memory row unmutated exactly as the real one does.

DB-backed, so ``TestCase`` and the integration tier (``backend/conftest.py``
auto-marks on that basis; no manual marker).
"""

import os
from datetime import timedelta
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from account_v2.models import Organization  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402
from utils.user_context import UserContext  # noqa: E402

from agent_kv.models import AgentKVJob, JobExtractor, JobStatus  # noqa: E402

_INPUT = "unstract/agent_kv/org/job/input.pdf"
_RESULT = "unstract/agent_kv/org/job/result-abc.json"


class _Rows(TestCase):
    """Shared real-row scaffolding."""

    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        # A cancelled job keeps its staged input until TTL, so a live one is the
        # realistic default. Note that NOTHING here reads `input_ref` to decide
        # whether a result may be attached -- that was attempt 2, and it was
        # unsound; these tests pin that it stays gone.
        kwargs.setdefault("input_ref", _INPUT)
        job = AgentKVJob(
            organization_id=self.org.id, extractor=JobExtractor.TABLE, **kwargs
        )
        job.save()
        return job


class TestTheSalvageAttachesAPaidForResult(_Rows):
    def test_a_cancelled_job_gets_its_result(self):
        job = self._job(status=JobStatus.CANCELLED)

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT, usage_summary={"pages": 3}
        )
        job.refresh_from_db()

        assert attached is True
        assert job.result_ref == _RESULT
        assert job.usage_summary == {"pages": 3}

    def test_it_never_changes_status_or_completed_at(self):
        """The cancel stays won, and stays visible.

        ``mark_terminal`` is the only way to reach a terminal state. If this
        ever starts flipping `status`, a cancelled job reads as completed and
        that guard has been bypassed through the back door.
        """
        stamped = timezone.now()
        job = self._job(status=JobStatus.CANCELLED, completed_at=stamped)

        AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref=_RESULT)
        job.refresh_from_db()

        assert job.status == JobStatus.CANCELLED
        assert job.completed_at == stamped

    def test_a_completed_or_failed_job_is_left_alone(self):
        """Scoped to CANCELLED on purpose: a COMPLETED or FAILED row already
        owns its outcome, and grafting a late callback's result onto it would
        overwrite a real one or invent one for a run that failed.
        """
        for status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job = self._job(status=status)
            attached = AgentKVJob.attach_result_to_cancelled(
                job.id, self.org.id, result_ref=_RESULT
            )
            job.refresh_from_db()
            assert attached is False, status
            assert job.result_ref == "", status

    def test_a_second_callback_does_not_overwrite_the_first(self):
        """At-least-once delivery means this runs twice. The second must report
        False so its caller deletes the file IT just wrote rather than orphaning
        it.
        """
        job = self._job(status=JobStatus.CANCELLED)

        first = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT
        )
        second = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref="unstract/agent_kv/org/job/result-def.json"
        )
        job.refresh_from_db()

        assert (first, second) == (True, False)
        assert job.result_ref == _RESULT

    def test_a_blank_ref_is_refused_so_the_caller_keeps_its_delete(self):
        job = self._job(status=JobStatus.CANCELLED)

        assert (
            AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref="")
            is False
        )

    def test_another_org_cannot_attach_a_result(self):
        other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        job = self._job(status=JobStatus.CANCELLED)

        assert (
            AgentKVJob.attach_result_to_cancelled(job.id, other.id, result_ref=_RESULT)
            is False
        )
        job.refresh_from_db()
        assert job.result_ref == ""


class TestThePurgeGuard(_Rows):
    """A result the caller DELETEd must never come back.

    This is the invariant that killed the three previous attempts, so each test
    here names the attempt it corresponds to.
    """

    def test_a_purged_job_does_not_get_a_result_grafted_on(self):
        """Attempt 1's hole: gating on `result_ref=""` alone. DELETE blanks both
        refs, which left exactly the row that filter matched.
        """
        job = self._job(
            status=JobStatus.CANCELLED,
            input_ref="",
            result_ref="",
            files_purged=True,
        )

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT
        )
        job.refresh_from_db()

        assert attached is False, (
            "attached a result to a job the caller DELETEd; purged data must "
            "not become readable again"
        )
        assert job.result_ref == ""

    def test_a_purged_job_whose_file_delete_FAILED_is_also_refused(self):
        """Attempt 2's hole, and the reason the marker exists.

        `delete_job_files` deliberately KEEPS a ref whose object delete failed,
        so TTL cleanup has a handle to retry from. A purged job can therefore
        have a non-blank `input_ref` -- which is why `input_ref > ""` was never
        a sound "this job was not deleted" test, and why this row must still be
        refused.
        """
        job = self._job(
            status=JobStatus.CANCELLED,
            input_ref=_INPUT,  # the delete failed; the ref is the retry handle
            result_ref="",
            files_purged=True,
        )

        assert (
            AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref=_RESULT)
            is False
        )

    def test_a_cancelled_job_with_no_staged_input_still_gets_its_result(self):
        """The other half of attempt 2 being wrong: a blank `input_ref` is not
        evidence of a purge either, so it must not block the salvage.
        """
        job = self._job(status=JobStatus.CANCELLED, input_ref="", files_purged=False)

        assert (
            AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref=_RESULT)
            is True
        )


class TestTheMarkerItself(_Rows):
    def test_the_claim_sets_the_marker_and_returns_the_fresh_row(self):
        job = self._job(status=JobStatus.CANCELLED)
        # Someone else's write, invisible to `job`.
        AgentKVJob.objects.filter(id=job.id).update(result_ref=_RESULT)

        row = AgentKVJob.mark_files_purged(job.id, self.org.id)

        assert row is not None
        assert row.files_purged is True
        assert row.result_ref == _RESULT, (
            "the claim returned a stale row; DELETE would then delete files "
            "from a snapshot that predates the write it is racing"
        )
        job.refresh_from_db()
        assert job.files_purged is True

    def test_the_claim_is_idempotent(self):
        job = self._job(status=JobStatus.CANCELLED, files_purged=True)

        row = AgentKVJob.mark_files_purged(job.id, self.org.id)

        assert row.files_purged is True

    def test_another_org_cannot_claim_the_purge(self):
        other = Organization.objects.create(
            display_name="Other", organization_id="org_other", name="other"
        )
        job = self._job(status=JobStatus.CANCELLED)

        assert AgentKVJob.mark_files_purged(job.id, other.id) is None
        job.refresh_from_db()
        assert job.files_purged is False

    def test_both_sides_take_the_row_lock(self):
        """The lock is the mechanism; the sequential tests below only show the
        two ORDERINGS it permits.

        What they cannot show is that a concurrent pair is forced into one of
        those orderings rather than interleaving -- that needs two connections,
        and a threaded test for it would be timing-dependent. So this asserts
        the lock structurally instead: both statements must carry `FOR UPDATE`.
        Lose it on either side and the interleaving documented in
        `mark_files_purged` reopens -- a result file left in the bucket on a row
        whose ref was blanked, unreachable by every later sweep.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        job = self._job(status=JobStatus.CANCELLED)

        with CaptureQueriesContext(connection) as claim:
            AgentKVJob.mark_files_purged(job.id, self.org.id)
        with CaptureQueriesContext(connection) as salvage:
            AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref=_RESULT)

        assert any("FOR UPDATE" in q["sql"] for q in claim.captured_queries), (
            "the purge claim no longer locks the row; a salvage can interleave "
            "between its read and the blanking write"
        )
        assert any("FOR UPDATE" in q["sql"] for q in salvage.captured_queries), (
            "the salvage no longer locks the row; the purge claim can read it "
            "between this guard and its write"
        )

    def test_the_claim_ordered_before_a_late_salvage_refuses_it(self):
        """The ordering the whole fix rests on, played out in sequence.

        A real DELETE and a real late finalize interleave; this asserts the only
        two outcomes that ordering permits. Here the purge lands first, so the
        salvage must be refused outright -- its caller then deletes the file it
        wrote, and nothing is orphaned and nothing purged is readable.
        """
        job = self._job(status=JobStatus.CANCELLED)

        AgentKVJob.mark_files_purged(job.id, self.org.id)
        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT
        )

        assert attached is False
        job.refresh_from_db()
        assert job.result_ref == ""

    def test_a_salvage_that_lands_first_is_visible_to_the_claim(self):
        """The other permitted outcome: the salvage committed before the purge
        read the row, so the purge SEES its ref and deletes that file too. This
        is what replaces the old "the late finalize cleans up its own write".
        """
        job = self._job(status=JobStatus.CANCELLED)

        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT
        )
        row = AgentKVJob.mark_files_purged(job.id, self.org.id)

        assert attached is True
        assert row.result_ref == _RESULT, (
            "the purge cannot see the result it has to delete; the file would "
            "stay in the bucket on a row whose ref is then blanked"
        )


class TestDeleteEndToEnd(_Rows):
    """`DELETE /agent-kv/{job_id}` against real rows."""

    def _delete(self, job):
        from agent_kv.execution_views import JobStatusView

        view = JobStatusView()
        # The key validator and the object store are the only externals here;
        # everything else runs for real.
        with mock.patch("agent_kv.execution_views._get_job", return_value=job):
            with mock.patch(
                "agent_kv.execution_views.delete_job_files"
            ) as m_delete_files:
                m_delete_files.side_effect = self._delete_files
                resp = JobStatusView.delete.__wrapped__(
                    view, mock.Mock(), job_id=job.id, agent_kv_key=mock.Mock()
                )
        return resp

    @staticmethod
    def _delete_files(row):
        """Stand-in for the object store: both deletes succeed."""
        return ["input_ref", "result_ref"]

    def test_delete_marks_the_job_purged(self):
        job = self._job(status=JobStatus.CANCELLED, result_ref=_RESULT)

        resp = self._delete(job)

        assert resp.status_code == 204
        job.refresh_from_db()
        assert job.files_purged is True
        assert (job.input_ref, job.result_ref) == ("", "")

    def test_delete_marks_the_job_purged_even_when_a_file_delete_FAILED(self):
        """The marker records intent, not outcome.

        This is the case a ref-based check cannot see: the result ref survives
        as TTL cleanup's retry handle, so "ref is blank" is not available as a
        purge signal -- and without the marker this job went on SERVING that
        result from the file that is still in the bucket.
        """
        job = self._job(status=JobStatus.CANCELLED, result_ref=_RESULT)

        from agent_kv.execution_views import JobStatusView

        view = JobStatusView()
        with mock.patch("agent_kv.execution_views._get_job", return_value=job):
            with mock.patch(
                "agent_kv.execution_views.delete_job_files",
                # Input gone; the result delete raised inside delete_job_files.
                return_value=["input_ref"],
            ):
                resp = JobStatusView.delete.__wrapped__(
                    view, mock.Mock(), job_id=job.id, agent_kv_key=mock.Mock()
                )

        assert resp.status_code == 204
        job.refresh_from_db()
        assert job.files_purged is True
        assert job.result_ref == _RESULT, "the retry handle must survive"

    def test_a_purged_job_refuses_a_later_salvage(self):
        """The invariant, end to end: DELETE then a late finalize."""
        job = self._job(status=JobStatus.CANCELLED, input_ref=_INPUT)

        self._delete(job)
        attached = AgentKVJob.attach_result_to_cancelled(
            job.id, self.org.id, result_ref=_RESULT
        )

        assert attached is False


class TestTheTtlSweepClaimsThePurge(_Rows):
    def _expired(self, **kwargs):
        kwargs.setdefault("status", JobStatus.CANCELLED)
        kwargs.setdefault("expires_at", timezone.now() - timedelta(days=1))
        return self._job(**kwargs)

    def test_ttl_cleanup_marks_every_row_it_processes(self):
        from agent_kv import maintenance

        job = self._expired(result_ref=_RESULT)

        with mock.patch.object(
            maintenance, "delete_job_files", return_value=["input_ref", "result_ref"]
        ):
            out = maintenance.run_ttl_cleanup()

        assert out["cleaned"] == 1
        job.refresh_from_db()
        assert job.files_purged is True

    def test_ttl_cleanup_marks_the_row_even_when_a_delete_FAILED(self):
        """Same reason as DELETE's: the ref is kept for a retry, so the marker
        is the only record that this job's data was swept.
        """
        from agent_kv import maintenance

        job = self._expired(result_ref=_RESULT)

        with mock.patch.object(
            maintenance, "delete_job_files", return_value=["input_ref"]
        ):
            out = maintenance.run_ttl_cleanup()

        assert out["retained"] == 1
        job.refresh_from_db()
        assert job.files_purged is True
        assert job.result_ref == _RESULT

    def test_ttl_cleanup_sees_a_result_attached_before_its_read(self):
        """No storage orphan: a salvage that committed before the sweep read the
        row has its file deleted along with everything else.

        The ordering is what guarantees it -- the sweep stamps the marker and
        re-reads under the same lock, so an attach is either visible here or
        refused. Without that, the sweep blanked a ref whose file it never
        deleted, and its own candidate filter (`input_ref > "" OR result_ref >
        ""`) could never select the row again: extracted customer data left in
        the bucket past its retention window.
        """
        from agent_kv import maintenance

        job = self._expired()
        AgentKVJob.attach_result_to_cancelled(job.id, self.org.id, result_ref=_RESULT)

        seen: list[str] = []

        def _record(row):
            seen.append(row.result_ref)
            return ["input_ref", "result_ref"]

        with mock.patch.object(maintenance, "delete_job_files", side_effect=_record):
            maintenance.run_ttl_cleanup()

        assert seen == [_RESULT]
        job.refresh_from_db()
        assert job.result_ref == ""


class TestTheFinalizeCallbackEndToEnd(_Rows):
    """The whole race, driven through `FinalizeView` against real rows.

    This is the shape that matters and the one a unit test of
    `attach_result_to_cancelled` cannot show: `FinalizeView.post` short-circuits
    on an already-terminal row, so a salvage that lives only on the
    guard-loss branch never runs for the real race -- the executor learns of a
    cancel from its FINAL stage report, so the row has read CANCELLED for a
    whole round trip by the time finalize is called.
    """

    def _finalize(self, job, body):
        """Drive the real view; only the object store is stood in for.

        `delete_input` is patched to REPORT SUCCESS rather than left to the real
        storage layer. Unpatched it raises, is swallowed, and returns False --
        so a salvage that wrongly dropped the staged input would leave
        `input_ref` set anyway and
        `test_the_cancelled_job_keeps_its_staged_input` would pass while the bug
        was present. Mutation-checked: adding a `_drop_staged_input` call to the
        salvage route must turn that test red.
        """
        from rest_framework.test import APIRequestFactory

        from agent_kv import internal_views as iv

        request = APIRequestFactory().post("/x", body, format="json")
        with mock.patch.object(iv.AgentKVConcurrencyLimiter, "release"):
            with mock.patch.object(iv, "write_result", return_value=_RESULT):
                with mock.patch.object(iv, "delete_input", return_value=True):
                    with mock.patch.object(iv, "delete_result_file") as m_del:
                        resp = iv.FinalizeView.as_view()(request, job_id=job.id)
        return resp, m_del

    def _body(self, **extra):
        body = {
            "org_id": str(self.org.id),
            "success": True,
            "result": {"tables": [{"rows": 12}]},
            "usage_summary": {"pages": 3},
        }
        body.update(extra)
        return body

    def test_a_success_callback_for_a_cancelled_job_stores_its_result(self):
        job = self._job(status=JobStatus.CANCELLED)

        resp, m_del = self._finalize(job, self._body())
        job.refresh_from_db()

        assert resp.status_code == 200
        assert resp.data["finalized"] is False
        assert resp.data["result_attached"] is True
        assert job.status == JobStatus.CANCELLED, "the cancel must stay won"
        assert job.result_ref == _RESULT
        assert job.usage_summary == {"pages": 3}
        assert not m_del.called

    def test_the_cancelled_job_keeps_its_staged_input(self):
        """`_drop_staged_input` stays gated on a won guard: a cancelled job's
        input rides the TTL sweep (docs section 9), and the salvage must not
        quietly change that.
        """
        job = self._job(status=JobStatus.CANCELLED)

        self._finalize(job, self._body())
        job.refresh_from_db()

        assert job.input_ref == _INPUT

    def test_a_duplicate_callback_deletes_its_own_write(self):
        job = self._job(status=JobStatus.CANCELLED)

        self._finalize(job, self._body())
        resp, m_del = self._finalize(job, self._body())
        job.refresh_from_db()

        assert resp.data["result_attached"] is False
        m_del.assert_called_once_with(_RESULT)
        assert job.result_ref == _RESULT, "the first write must stand"

    def test_a_callback_for_a_purged_job_deletes_its_own_write(self):
        """The invariant three attempts broke: a purged job serves nothing, and
        a late callback must not leave its file behind either.
        """
        job = self._job(status=JobStatus.CANCELLED, files_purged=True)

        resp, m_del = self._finalize(job, self._body())
        job.refresh_from_db()

        assert resp.data["result_attached"] is False
        m_del.assert_called_once_with(_RESULT)
        assert job.result_ref == ""


class TestWhatTheResultEndpointServes(_Rows):
    def _get_result(self, job):
        from agent_kv.execution_views import JobResultView

        view = JobResultView()
        with mock.patch("agent_kv.execution_views._get_job", return_value=job):
            return JobResultView.get.__wrapped__(
                view, mock.Mock(), job_id=job.id, agent_kv_key=mock.Mock()
            )

    def _fresh(self, **kwargs):
        kwargs.setdefault("expires_at", timezone.now() + timedelta(days=1))
        return self._job(**kwargs)

    def test_a_salvaged_result_is_served_with_status_cancelled(self):
        """`status` stays `cancelled` -- the cancel WAS honoured and a client
        must be able to see it -- while `success` is True, because there is a
        real result and it was paid for.
        """
        job = self._fresh(status=JobStatus.CANCELLED, result_ref=_RESULT)

        with mock.patch(
            "agent_kv.execution_views_result.read_result",
            return_value={"tables": [], "row_count": 0},
        ):
            resp = self._get_result(job)

        assert resp.status_code == 200
        assert resp.data["status"] == "cancelled"
        assert resp.data["success"] is True
        assert resp.data["extractors"]["table"] == {"tables": [], "row_count": 0}

    def test_an_ordinary_cancel_is_byte_identical_to_before(self):
        """The common path -- cancelled mid-run, nothing computed -- must not
        change shape just because the salvage exists.
        """
        job = self._fresh(status=JobStatus.CANCELLED)

        resp = self._get_result(job)

        assert resp.data == {"success": False, "status": "cancelled"}

    def test_a_purged_cancelled_job_serves_nothing(self):
        job = self._fresh(
            status=JobStatus.CANCELLED, result_ref=_RESULT, files_purged=True
        )

        with mock.patch("agent_kv.execution_views_result.read_result") as m_read:
            from agent_kv.exceptions import JobNotFound

            with self.assertRaises(JobNotFound):
                self._get_result(job)

        assert not m_read.called

    def test_a_purged_COMPLETED_job_whose_delete_failed_serves_nothing(self):
        """The pre-existing hole the marker also closes.

        `delete_job_files` keeps a ref whose object delete failed, so a DELETE
        that could not remove the result file left `result_ref` set on a
        COMPLETED row -- and this endpoint went on reading that very file. The
        blank-ref check cannot see this case; only the marker can.
        """
        job = self._fresh(
            status=JobStatus.COMPLETED, result_ref=_RESULT, files_purged=True
        )

        from agent_kv.exceptions import JobNotFound

        with self.assertRaises(JobNotFound):
            self._get_result(job)
