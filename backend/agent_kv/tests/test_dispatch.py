import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402

from agent_kv import dispatch  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _job():
    j = AgentKVJob(id=uuid.uuid4(), input_ref="org/o/agent_kv/j/input.pdf")
    j.organization_id = "org1"
    j.pages_total = 3
    return j


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "save")
def test_dispatch_success_stamps_job(m_save, m_disp, m_key):
    job = _job()
    dispatch.dispatch_job(job, schema={"a": {"description": "d"}}, options={"qa": True})

    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_kv"
    assert ctx.operation == "kv_extract"
    assert ctx.run_id == str(job.id)
    assert ctx.execution_source == "agent_kv_api"
    assert ctx.organization_id == "org1"
    assert ctx.executor_params["job_id"] == str(job.id)
    assert ctx.executor_params["input_ref"] == job.input_ref
    assert ctx.executor_params["schema"] == {"a": {"description": "d"}}
    assert ctx.executor_params["options"] == {"qa": True}
    assert ctx.executor_params["platform_api_key"] == "pk"
    assert ctx.executor_params["max_pages"] == 3

    kw = m_disp.return_value.dispatch_with_callback.call_args.kwargs
    assert kw["on_success"].task == "agent_kv_complete"
    assert kw["on_success"].kwargs == {
        "callback_kwargs": {"job_id": str(job.id), "org_id": "org1"}
    }
    assert kw["on_success"].options.get("queue") == "agent_kv_callback"
    assert kw["on_error"].task == "agent_kv_error"
    assert kw["on_error"].kwargs == {
        "callback_kwargs": {"job_id": str(job.id), "org_id": "org1"}
    }
    assert kw["task_id"] == str(job.task_id)

    assert job.status == JobStatus.DISPATCHED
    assert job.dispatched_at is not None
    assert m_save.called
    save_kwargs = m_save.call_args.kwargs
    assert set(save_kwargs["update_fields"]) == {
        "task_id",
        "status",
        "dispatched_at",
        "modified_at",
    }


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
        with mock.patch.object(AgentKVJob, "save"):
            dispatch.dispatch_job(job, schema={}, options={})
        ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
        assert ctx.executor_params["platform_api_key"] == "the-real-key"


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
            dispatch._platform_api_key("org1")
