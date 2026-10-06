import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from django.conf import settings  # noqa: E402

from agent_kv import dispatch  # noqa: E402
from agent_kv.constants import TABLE_EXTRACTOR_NAME  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _fail_only_bookkeeping(m_objects, exc):
    """Let the pre-dispatch terminal check succeed, then fail the next query.

    These tests are about a DB error during POST-ENQUEUE bookkeeping, which
    must not be reported as a failed dispatch. A blanket `filter.side_effect`
    now hits the pre-dispatch terminal check instead -- a different, earlier
    failure that correctly DOES abort the dispatch, since a job that cannot be
    verified as live must not have money spent on it.
    """
    live = mock.MagicMock()
    live.exists.return_value = False
    m_objects.filter.side_effect = [live, exc]


def _filtered_with(m_objects, **expected):
    """True if `objects.filter` was ever called with exactly these kwargs.

    Content-based rather than positional: `dispatch_job` makes several filter
    calls (the pre-dispatch terminal check, the guarded bookkeeping UPDATE, and
    on the slow path a narrowed fallback), and index-pinned assertions broke
    every time one was added.
    """
    return any(call.kwargs == expected for call in m_objects.filter.call_args_list)


def _not_cancelled(m_objects):
    """Make the pre-dispatch terminal check report "still live".

    `dispatch_job` re-reads the row immediately before enqueueing, so a cancel
    that landed between the submit's save() and the enqueue cannot result in
    paid work for a job whose slot was already released. With `objects` mocked
    the default `.exists()` is a truthy Mock, which would short-circuit every
    dispatch in this file.
    """
    m_objects.filter.return_value.exists.return_value = False


def _job():
    from account_v2.models import Organization

    j = AgentKVJob(id=uuid.uuid4(), input_ref="org/o/agent_kv/j/input.pdf")
    # Unsaved related org with an explicit PK: assigning it caches the
    # instance on the job (so ``job.organization`` never hits the DB) and
    # sets ``job.organization_id`` to 7; the slug is deliberately different
    # from the PK so a test can tell them apart.
    j.organization = Organization(id=7, organization_id="org_slug_1")  # PK 7
    j.pages_total = 3
    return j


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_dispatch_success_stamps_job(m_objects, m_disp, m_key):
    _not_cancelled(m_objects)
    job = _job()
    dispatch.dispatch_job(
        job,
        extractor=TABLE_EXTRACTOR_NAME,
        schema={"a": {"description": "d"}},
        options={"number_format": "EU"},
    )

    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_table"
    assert ctx.operation == "table_extract_api"
    assert ctx.run_id == str(job.id)
    assert ctx.execution_source == "agent_kv_api"
    assert ctx.organization_id == "7"
    assert ctx.executor_params["job_id"] == str(job.id)
    assert ctx.executor_params["input_ref"] == job.input_ref
    assert ctx.executor_params["schema"] == {"a": {"description": "d"}}
    assert ctx.executor_params["options"] == {"number_format": "EU"}
    assert ctx.executor_params["platform_api_key"] == "pk"
    # max_pages is the CAP the engine must enforce, not the measured count
    # (job.pages_total, which rides separately and is None for Excel).
    assert ctx.executor_params["max_pages"] == settings.AGENT_KV_MAX_PAGES
    assert ctx.executor_params["pages_total"] == 3

    kw = m_disp.return_value.dispatch_with_callback.call_args.kwargs
    assert kw["on_success"].task == "agent_kv_complete"
    assert kw["on_success"].kwargs == {
        "callback_kwargs": {"job_id": str(job.id), "org_id": "7"}
    }
    assert kw["on_success"].options.get("queue") == "agent_kv_callback"
    assert kw["on_error"].task == "agent_kv_error"
    assert kw["on_error"].kwargs == {
        "callback_kwargs": {"job_id": str(job.id), "org_id": "7"}
    }
    assert kw["task_id"] == str(job.task_id)

    assert job.status == JobStatus.DISPATCHED
    assert job.dispatched_at is not None
    # Guarded queryset UPDATE (not job.save()): only a still-PENDING row may
    # be advanced to DISPATCHED.
    # The pre-dispatch terminal check filters first; the guarded bookkeeping
    # UPDATE is the last filter call.
    assert _filtered_with(m_objects, id=job.id, status=JobStatus.PENDING)
    m_objects.filter.return_value.update.assert_called_once_with(
        task_id=job.task_id,
        status=JobStatus.DISPATCHED,
        dispatched_at=job.dispatched_at,
    )


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_dispatch_guarded_update_cannot_overwrite_a_terminal_row(
    m_objects, m_disp, m_key
):
    """Regression for the un-terminalize bug: if the row already raced to a
    terminal status (e.g. FAILED, via an instant-failure finalize callback
    that beat this post-enqueue bookkeeping), the guarded UPDATE's WHERE
    clause (status=PENDING) structurally cannot match it -- 0 rows update,
    and the row's real status is left untouched. Proven the same way
    ``AgentKVJob.mark_terminal``'s own guard is proven (test_models.py): by
    pinning the exact WHERE-clause kwargs and simulating the "no rows
    matched" outcome, since this suite runs with no real DB.
    """
    _not_cancelled(m_objects)
    m_objects.filter.return_value.update.return_value = 0  # simulates a FAILED row
    job = _job()

    # Must not raise -- dispatch_job doesn't (and can't meaningfully) act on
    # the update's row count; it already told the caller it dispatched.
    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    assert _filtered_with(m_objects, id=job.id, status=JobStatus.PENDING)
    # The 0-row result now triggers a SECOND guarded write (below), whose
    # `.exclude(status__in=TERMINAL)` is what keeps a terminal row untouched
    # here -- so the terminal case is still structurally safe.
    (_, excl_kwargs) = (
        m_objects.filter.return_value.exclude.call_args.args,
        m_objects.filter.return_value.exclude.call_args.kwargs,
    )
    assert set(excl_kwargs["status__in"]) == set(AgentKVJob.TERMINAL)


# The stranded-job regression. `StageReportView` promotes PENDING -> RUNNING on
# the executor's first stage report, which can land before this post-enqueue
# bookkeeping. The PENDING-guarded UPDATE then matches 0 rows and
# `dispatched_at` stays NULL -- and a non-terminal row with a NULL
# `dispatched_at` is invisible to BOTH sweep phases (phase 1 requires PENDING;
# phase 2's `dispatched_at__lt` can never match a NULL), so the job reports
# `running` forever and `GET result` 409s for the life of the row.
@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_dispatch_stamps_dispatched_at_when_the_row_already_moved_to_running(
    m_objects, m_disp, m_key
):
    _not_cancelled(m_objects)
    m_objects.filter.return_value.update.return_value = 0  # PENDING guard missed
    job = _job()

    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    # Second write is narrowed to a row that still has no dispatch time, and
    # excludes terminal rows.
    assert _filtered_with(m_objects, id=job.id, dispatched_at__isnull=True)
    fallback = m_objects.filter.return_value.exclude.return_value
    update_kwargs = fallback.update.call_args.kwargs
    assert update_kwargs["dispatched_at"] == job.dispatched_at
    assert update_kwargs["task_id"] == job.task_id
    # Crucially does NOT write `status`: the row genuinely was dispatched, but
    # moving RUNNING back to DISPATCHED would discard the executor's progress.
    assert "status" not in update_kwargs


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_dispatch_does_not_attempt_the_fallback_when_the_pending_guard_won(
    m_objects, m_disp, m_key
):
    _not_cancelled(m_objects)
    m_objects.filter.return_value.update.return_value = 1  # normal path
    job = _job()

    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    # Terminal check + the single guarded bookkeeping UPDATE; no fallback.
    assert len(m_objects.filter.call_args_list) == 2
    assert not m_objects.filter.return_value.exclude.called


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
def test_enqueue_failure_raises_dispatch_error(m_disp, m_key):
    m_disp.return_value.dispatch_with_callback.side_effect = RuntimeError("broker down")
    job = _job()
    with pytest.raises(dispatch.DispatchError):
        dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})


@mock.patch.object(dispatch, "_dispatcher")
def test_dispatch_job_uses_platform_api_key_lookup(m_disp):
    from platform_settings_v2.platform_auth_service import (
        PlatformAuthenticationService,
    )

    with mock.patch.object(
        PlatformAuthenticationService,
        "get_active_platform_key",
        return_value=mock.Mock(key="the-real-key"),
    ):
        job = _job()
        with mock.patch.object(AgentKVJob, "objects") as m_objects:
            # Without this the pre-dispatch terminal check reads a truthy Mock
            # and short-circuits, so nothing is ever enqueued.
            _not_cancelled(m_objects)
            dispatch.dispatch_job(
                job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={}
            )
        ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
        assert ctx.executor_params["platform_api_key"] == "the-real-key"
        # The lookup takes the org's public slug, never the row PK (13b F6).
        PlatformAuthenticationService.get_active_platform_key.assert_called_once_with(
            "org_slug_1"
        )
        assert ctx.organization_id == "7"


def test_platform_api_key_raises_dispatch_error_when_absent():
    from platform_settings_v2.platform_auth_service import (
        PlatformAuthenticationService,
    )

    with mock.patch.object(
        PlatformAuthenticationService,
        "get_active_platform_key",
        return_value=None,
    ):
        job = _job()
        with pytest.raises(dispatch.DispatchError):
            dispatch._platform_api_key(job)


@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(dispatch, "_platform_api_key")
def test_raw_exception_from_platform_key_lookup_is_wrapped_as_dispatch_error(
    m_key, m_disp
):
    """Regression: platform-key lookup and context construction must live
    inside dispatch_job's try — a raw (non-DispatchError) exception there
    (e.g. a transient DB error) must not escape uncaught.
    """
    m_key.side_effect = RuntimeError("platform db down")

    job = _job()
    with pytest.raises(dispatch.DispatchError):
        dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    # Never got far enough to enqueue.
    assert not m_disp.return_value.dispatch_with_callback.called


def test_dispatcher_factory_call_matches_the_live_signature():
    """Guard the OSS seam that a platform change can silently move.

    UN-4046 removed `get_executor_dispatcher(celery_app=...)`; our call site
    kept passing it, so every submit raised TypeError inside dispatch_job and
    failed the job. Nothing caught it -- the mismatch is invisible to a mocked
    dispatcher and only appears when a real request is made.

    Binding our actual call against the real signature fails loudly the next
    time that function's parameters change.
    """
    from unittest import mock  # noqa: PLC0415

    from agent_kv import dispatch as d  # noqa: PLC0415

    # autospec=True makes the stub enforce the REAL function's signature, so
    # this asserts our call site against it rather than against a permissive
    # Mock. Re-adding `celery_app=` here raises TypeError, exactly as production
    # did.
    with mock.patch(
        "pg_queue.executor_rpc.get_executor_dispatcher", autospec=True
    ) as m_factory:
        d._dispatcher()
    m_factory.assert_called_once_with()


# Post-enqueue bookkeeping must never fail a dispatch that already succeeded.
# `SubmitView` turns a DispatchError into a FAILED job, so a DB hiccup here
# would terminalize a job whose task is on the queue -- the executor then runs,
# calls back, and finds a terminal row it cannot write to, while the caller was
# told nothing was billed for work that did run. The review round added a
# SECOND update after the enqueue, which widened this window.
@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_bookkeeping_failure_does_not_fail_an_already_queued_dispatch(
    m_objects, m_disp, m_key
):
    _not_cancelled(m_objects)
    _fail_only_bookkeeping(m_objects, OSError("db gone"))
    job = _job()

    # Must not raise: raising is what would mark the live job FAILED.
    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    # And the enqueue did happen, so the task is genuinely on the queue.
    assert m_disp.return_value.dispatch_with_callback.called


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_bookkeeping_failure_is_logged_at_error_level(m_objects, m_disp, m_key, caplog):
    """Swallowing it silently would trade one bad failure mode for another:
    the sweep reconciles the row, but nothing would say why it had to.
    """
    _not_cancelled(m_objects)
    _fail_only_bookkeeping(m_objects, OSError("db gone"))
    with caplog.at_level("ERROR", logger=dispatch.logger.name):
        dispatch.dispatch_job(
            _job(), extractor=TABLE_EXTRACTOR_NAME, schema={}, options={}
        )
    assert any(r.levelname == "ERROR" and r.exc_info for r in caplog.records)


# ---------------------------------------------------------------------------
# A job cancelled between submit's save() and the enqueue must not be dispatched.
#
# The cancel sees a PENDING, never-dispatched row, so it terminalizes it AND
# releases its concurrency slot -- correctly, nothing had been dispatched yet.
# Enqueueing anyway would then run paid work for a job the caller already
# cancelled, with its slot already handed to the next submit: the concurrency
# ceiling bypassed and the customer billed for a cancelled job.
#
# Reported by Greptile on PR #2317.
# ---------------------------------------------------------------------------
@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_a_job_cancelled_before_enqueue_is_not_dispatched(m_objects, m_disp, m_key):
    job = _job()
    m_objects.filter.return_value.exists.return_value = True  # already terminal

    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    assert (
        not m_disp.return_value.dispatch_with_callback.called
    ), "paid work was enqueued for a job that was already cancelled"
    # And no bookkeeping UPDATE either -- there is nothing to advance.
    assert not m_objects.filter.return_value.update.called


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_the_terminal_check_reads_the_row_rather_than_the_in_memory_copy(
    m_objects, m_disp, m_key
):
    """The in-memory job predates the cancel by construction, so trusting
    `job.status` here would never see it.
    """
    job = _job()
    job.status = JobStatus.PENDING  # stale: the row may already be CANCELLED
    _not_cancelled(m_objects)

    dispatch.dispatch_job(job, extractor=TABLE_EXTRACTOR_NAME, schema={}, options={})

    assert _filtered_with(m_objects, id=job.id, status__in=list(AgentKVJob.TERMINAL))
