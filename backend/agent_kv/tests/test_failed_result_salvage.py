"""A FAILED job keeps the extraction it already billed for.

The defect: the `kv` engine fails a job whose `calculations` run failed --
correctly, since the caller asked for calculations and did not get them -- but
the extraction itself had succeeded and its OCR and LLM spend was already
flushed. The executor hands that record over on purpose rather than destroying
it (`agentic_kv/src/executor.py`: "reporting a failure and destroying the
extraction are two different things, and only the second is a defect"), and it
then died twice on the way out:

1. ``ide_callback.agent_kv_tasks.agent_kv_complete``'s failure arm called
   finalize with ``error`` and never passed ``data``.
2. ``FinalizeView._fail`` wrote the error and nothing else, documenting that
   "there is no result to attach to anything on a failure".

So the customer paid for an extraction and ``GET result`` answered
``{"success": false, "status": "failed", "error": ...}``.

**``success`` stays False.** The job really did fail, and flipping it would be a
BREAKING change: a client branching on ``success`` to decide whether to run its
error path would stop running it. The extraction is additive instead, behind
``extraction_salvaged``. That is the opposite call from the cancelled race
(`test_cancelled_result_salvage.py`), which DOES report ``success: True`` -- and
deliberately so: nothing the caller asked for failed there.

The row/guard tests are DB-backed for the reason that file gives at length: the
mechanisms are guarded UPDATEs, and a mocked ``mark_terminal`` leaves the
in-memory row unmutated exactly as the real one does, so a mock agrees with
whichever condition happened to be written. The orphan-delete tests are the one
case that cannot be reached with real rows -- they need the guard to lose
between the write and the UPDATE -- so they mock precisely that and nothing
else.

DB-backed, so ``TestCase`` and the integration tier (``backend/conftest.py``
auto-marks on that basis; no manual marker).
"""

import os
import uuid
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
from rest_framework.test import APIRequestFactory  # noqa: E402
from utils.user_context import UserContext  # noqa: E402

from agent_kv import execution_views as ev  # noqa: E402
from agent_kv import execution_views_result as evr  # noqa: E402
from agent_kv import internal_views as iv  # noqa: E402
from agent_kv.execution_views_result import result_payload  # noqa: E402
from agent_kv.models import (  # noqa: E402
    AgentKVJob,
    AgentKVKey,
    JobExtractor,
    JobStatus,
)
from agent_kv.tests._factories import kv_key  # noqa: E402

_RESULT = "unstract/agent_kv/org/job/result-abc.json"

#: What the executor actually hands over: the engine's own fields, FLAT -- not
#: wrapped in `{"output": ...}` the way the success arm's `data` is. Taken from
#: the `salvage` dict in `agentic_kv/src/executor.py`; `success`/`error` ride
#: with it because the engine sets them on the same object.
_SALVAGE = {
    "success": False,
    "error": "executor failed: calculation execution timed out",
    "record": {"invoice_number": "INV-9", "total": "1234.56"},
    "normalized_record": {"invoice_number": "INV-9", "total": "1234.56"},
    "keys": [{"key_path": "invoice_number", "qa_status": "passed"}],
    "qa_passed": True,
    "challenge_passed": True,
}


def _post(body):
    return APIRequestFactory().post("/x", body, format="json")


def _authed():
    req = APIRequestFactory().get("/api/v1/agentic-extract/x")
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


class _Rows(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            display_name="Acme", organization_id="org_acme", name="acme"
        )
        UserContext.set_organization_identifier(None)

    def _job(self, **kwargs):
        kwargs.setdefault("status", JobStatus.RUNNING)
        kwargs.setdefault("extractor", JobExtractor.KV)
        job = AgentKVJob(organization_id=self.org.id, **kwargs)
        job.save()
        return job

    def _finalize(self, job, body):
        return iv.FinalizeView.as_view()(_post(body), job_id=job.id)


class TestAFailedFinalizeKeepsASalvagedExtraction(_Rows):
    @mock.patch.object(iv, "write_result", return_value=_RESULT)
    def test_the_result_is_written_and_the_ref_stored(self, m_write):
        job = self._job()

        resp = self._finalize(
            job,
            {
                "org_id": str(self.org.id),
                "success": False,
                "error": "boom",
                "result": _SALVAGE,
            },
        )
        job.refresh_from_db()

        assert resp.status_code == 200
        assert resp.data["finalized"] is True
        assert job.status == JobStatus.FAILED
        assert job.error == "boom"
        assert job.result_ref == _RESULT
        m_write.assert_called_once_with(str(self.org.id), str(job.id), _SALVAGE)

    @mock.patch.object(iv, "write_result")
    def test_an_ordinary_failure_still_writes_nothing(self, m_write):
        """The no-salvage path must be untouched -- no write, no ref, no file.

        `test_internal_views.test_finalize_failure_records_error` pins the
        `mark_terminal` call argument-for-argument for the same reason; this
        pins the row it produces.
        """
        job = self._job()

        self._finalize(job, {"org_id": str(self.org.id), "success": False, "error": "x"})
        job.refresh_from_db()

        assert not m_write.called
        assert job.status == JobStatus.FAILED
        assert job.result_ref == ""

    @mock.patch.object(iv, "write_result")
    def test_an_empty_result_is_not_a_salvage(self, m_write):
        """`{}` must behave as absent, not as "write an empty result file".

        The executor sends `data={}` on every failure that has nothing to
        salvage, and its own comment records that it deliberately does NOT
        guard the call site on `if salvage:` -- so an empty dict arrives here
        routinely and must not produce a file.
        """
        job = self._job()

        self._finalize(
            job,
            {"org_id": str(self.org.id), "success": False, "error": "x", "result": {}},
        )
        job.refresh_from_db()

        assert not m_write.called
        assert job.result_ref == ""

    @mock.patch.object(iv, "write_result", return_value=_RESULT)
    def test_the_staged_input_is_still_dropped(self, _m_write):
        """Salvaging a result does not keep the uploaded document alive.

        The run is over either way (spec D10), and the input is deleted the
        moment the guard is won. Only the RESULT now survives a failure.
        """
        job = self._job(input_ref="unstract/agent_kv/org/job/input.pdf")

        with mock.patch.object(iv, "delete_input", return_value=True) as m_del:
            self._finalize(
                job,
                {
                    "org_id": str(self.org.id),
                    "success": False,
                    "error": "boom",
                    "result": _SALVAGE,
                },
            )
        job.refresh_from_db()

        assert m_del.called
        assert job.input_ref == ""
        assert job.result_ref == _RESULT


class TestTheOrphanIsCleanedUpWhenTheGuardIsLost(TestCase):
    """The one case real rows cannot reach: a cancel or duplicate wins between
    ``write_result`` and ``mark_terminal``, so the file this request wrote is
    referenced by nothing.

    ``write_result`` has to run first -- there is no ref to pass into the guard
    until it has -- which is the same ordering ``_complete`` has always had.
    """

    @mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
    @mock.patch.object(iv, "delete_result_file")
    @mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
    @mock.patch.object(iv, "write_result", return_value=_RESULT)
    @mock.patch.object(AgentKVJob, "objects")
    def test_a_lost_guard_deletes_the_file_it_wrote(
        self, m_jobs, _m_write, _m_mark, m_delete, _m_release
    ):
        m_jobs.filter.return_value.first.return_value = AgentKVJob(
            status=JobStatus.RUNNING, webhook_url=""
        )

        resp = iv.FinalizeView.as_view()(
            _post(
                {
                    "org_id": "org1",
                    "success": False,
                    "error": "boom",
                    "result": _SALVAGE,
                }
            ),
            job_id=uuid.uuid4(),
        )

        assert resp.data["finalized"] is False
        # Not `result_attached`: that means "kept on a row this request did not
        # terminalize", which is the cancelled race alone.
        assert resp.data["result_attached"] is False
        m_delete.assert_called_once_with(_RESULT)

    @mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
    @mock.patch.object(iv, "delete_result_file")
    @mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
    @mock.patch.object(iv, "write_result")
    @mock.patch.object(AgentKVJob, "objects")
    def test_a_lost_guard_with_no_salvage_deletes_nothing(
        self, m_jobs, m_write, _m_mark, m_delete, _m_release
    ):
        """Nothing was written, so there is nothing to delete -- and calling
        ``delete_result_file("")`` would ask storage to remove the job's own
        directory root.
        """
        m_jobs.filter.return_value.first.return_value = AgentKVJob(
            status=JobStatus.RUNNING, webhook_url=""
        )

        iv.FinalizeView.as_view()(
            _post({"org_id": "org1", "success": False, "error": "boom"}),
            job_id=uuid.uuid4(),
        )

        assert not m_write.called
        assert not m_delete.called


class TestTheResultEndpointServesIt(_Rows):
    @mock.patch.object(evr, "read_result", return_value=_SALVAGE)
    def test_a_salvaged_failure_carries_the_extraction(self, _m_read):
        job = self._job(status=JobStatus.FAILED, error="boom", result_ref=_RESULT)

        body = result_payload(job)

        # `success` stays False: the job failed. See this module's docstring
        # for why flipping it would be a breaking change.
        assert body["success"] is False
        assert body["status"] == "failed"
        assert body["error"] == "boom"
        assert body["extraction_salvaged"] is True
        assert body["extractors"] == {JobExtractor.KV: _SALVAGE}
        # None is sent on this path -- neither salvaging executor branch has
        # computed one by the time it gives up. Absent rather than zeroed, so
        # it cannot read as "this cost nothing".
        assert "usage_summary" not in body

    def test_an_ordinary_failure_is_unchanged(self):
        """Byte-identical to the shape every existing client already handles."""
        job = self._job(status=JobStatus.FAILED, error="boom")

        assert result_payload(job) == {
            "success": False,
            "status": "failed",
            "error": "boom",
        }


class TestRetentionAndPurgeStillWin(TestCase):
    """A salvaged result is customer data in a bucket, so it obeys the same
    rules as a completed one.

    ``JobResultView`` gates on ``files_purged`` and ``expires_at`` before it
    ever calls ``result_payload``; these pin that a FAILED row carrying a ref
    does not slip past either gate. Without them, "a FAILED job may now have a
    ``result_ref``" would be a quiet way for extracted output to outlive a
    DELETE or its retention window.
    """

    def _failed_job(self, **kwargs):
        kwargs.setdefault("expires_at", timezone.now() + timedelta(days=1))
        return AgentKVJob(
            extractor=JobExtractor.KV,
            status=JobStatus.FAILED,
            error="boom",
            result_ref=_RESULT,
            **kwargs,
        )

    @mock.patch.object(evr, "read_result", return_value=_SALVAGE)
    @mock.patch.object(AgentKVJob, "objects")
    @mock.patch.object(AgentKVKey, "objects")
    def test_it_is_served_while_live(self, m_keys, m_jobs, _m_read):
        m_keys.get.return_value = kv_key()
        m_jobs.get.return_value = self._failed_job()

        resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

        assert resp.status_code == 200
        assert resp.data["success"] is False
        assert resp.data["extraction_salvaged"] is True
        assert resp.data["extractors"] == {JobExtractor.KV: _SALVAGE}

    @mock.patch.object(evr, "read_result", return_value=_SALVAGE)
    @mock.patch.object(AgentKVJob, "objects")
    @mock.patch.object(AgentKVKey, "objects")
    def test_a_purged_salvage_is_404(self, m_keys, m_jobs, _m_read):
        m_keys.get.return_value = kv_key()
        m_jobs.get.return_value = self._failed_job(files_purged=True)

        resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

        assert resp.status_code == 404

    @mock.patch.object(evr, "read_result", return_value=_SALVAGE)
    @mock.patch.object(AgentKVJob, "objects")
    @mock.patch.object(AgentKVKey, "objects")
    def test_an_expired_salvage_is_404(self, m_keys, m_jobs, _m_read):
        m_keys.get.return_value = kv_key()
        m_jobs.get.return_value = self._failed_job(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

        assert resp.status_code == 404
