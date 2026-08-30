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
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


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
    job = _job()
    dispatch.dispatch_job(job, schema={"a": {"description": "d"}}, options={"qa": True})

    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_kv"
    assert ctx.operation == "kv_extract"
    assert ctx.run_id == str(job.id)
    assert ctx.execution_source == "agent_kv_api"
    assert ctx.organization_id == "7"
    assert ctx.executor_params["job_id"] == str(job.id)
    assert ctx.executor_params["input_ref"] == job.input_ref
    assert ctx.executor_params["schema"] == {"a": {"description": "d"}}
    assert ctx.executor_params["options"] == {"qa": True}
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
    m_objects.filter.assert_called_once_with(id=job.id, status=JobStatus.PENDING)
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
    m_objects.filter.return_value.update.return_value = 0  # simulates a FAILED row
    job = _job()

    # Must not raise -- dispatch_job doesn't (and can't meaningfully) act on
    # the update's row count; it already told the caller it dispatched.
    dispatch.dispatch_job(job, schema={}, options={})

    filter_kwargs = m_objects.filter.call_args.kwargs
    assert filter_kwargs == {"id": job.id, "status": JobStatus.PENDING}


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
def test_enqueue_failure_raises_dispatch_error(m_disp, m_key):
    m_disp.return_value.dispatch_with_callback.side_effect = RuntimeError("broker down")
    with pytest.raises(dispatch.DispatchError):
        dispatch.dispatch_job(_job(), schema={}, options={})


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
        with mock.patch.object(AgentKVJob, "objects"):
            dispatch.dispatch_job(job, schema={}, options={})
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
        with pytest.raises(dispatch.DispatchError):
            dispatch._platform_api_key(_job())


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

    with pytest.raises(dispatch.DispatchError):
        dispatch.dispatch_job(_job(), schema={}, options={})

    # Never got far enough to enqueue.
    assert not m_disp.return_value.dispatch_with_callback.called
