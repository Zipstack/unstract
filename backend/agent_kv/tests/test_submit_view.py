import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from agent_kv import execution_views as ev  # noqa: E402
from agent_kv.models import AgentKVJob, AgentKVKey, JobStatus  # noqa: E402
from agent_kv.tests._factories import kv_key  # noqa: E402


def _post(data=None):
    return APIRequestFactory().post("/agent-kv/", data or {}, format="multipart")


def _authed_post(data=None):
    req = _post(data)
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


# Fields describing the REQUEST rather than an extractor (spec §7.1); anything
# else an override names is routed into the kv extractor's options, so each test
# still reads as "submit with this one thing changed".
_JOB_LEVEL = {
    "file", "extractors", "page_start", "page_end",
    "timeout", "tags", "custom_data", "webhook_url",
}


def _valid_validated_data(**overrides):
    """`SubmitSerializer.validated_data` in the extractor-scoped shape (§7.0)."""
    keys = overrides.pop("keys", {"total": {"description": "Grand total"}})
    options = {
        "qa": True,
        "challenge": True,
        "extraction_mode": "whole-doc",
        "structured_output": False,
        "calculations": "",
        "document_class": "",
        "key_notes": "",
    }
    options.update({k: overrides.pop(k) for k in list(overrides) if k not in _JOB_LEVEL})
    data = {
        "file": mock.Mock(name="uploaded_file"),
        "extractors": [{"name": "kv", "keys": keys, "options": options}],
        "page_start": 1,
        "page_end": None,
        "timeout": 0,
        "tags": [],
        "custom_data": None,
        "webhook_url": "",
    }
    data.update(overrides)
    return data


def _mock_serializer(m_cls, **overrides):
    instance = m_cls.return_value
    instance.is_valid.return_value = True
    instance.validated_data = _valid_validated_data(**overrides)
    instance.pages_total = 3
    return instance


def _stamp_created_at(job, *args, **kwargs):
    """save() side effect mimicking auto_now_add for a fully-mocked save().

    A plain ``mock.patch.object(AgentKVJob, "save")`` never runs Django's real
    save() machinery, so ``created_at`` (auto_now_add) is never stamped. The
    view reads ``job.created_at.isoformat()`` on the 202 path, so tests that
    reach it need ``autospec=True`` (to get ``self``) plus this side effect.
    """
    if job.created_at is None:
        job.created_at = timezone.now()


# ---------------------------------------------------------------------------
# 501 before anything: the agent-kv plugin probe fails first, ahead of any
# staging/dispatch/DB work.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "get_plugin", return_value=None)
@mock.patch.object(AgentKVKey, "objects")
def test_absent_plugin_501s_before_anything(m_keys, m_plugin):
    m_keys.get.return_value = kv_key()
    resp = ev.SubmitView.as_view()(_authed_post())
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# 429: per-key rate limit refusal.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "check_key_rate", return_value=False)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_key_rate_limited_429s(m_keys, m_plugin, m_rate):
    m_keys.get.return_value = kv_key()
    resp = ev.SubmitView.as_view()(_authed_post())
    assert resp.status_code == 429
    assert m_rate.called


# ---------------------------------------------------------------------------
# 429: concurrency-slot refusal. No job row must be persisted (save() never
# called) and staging must never run.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_concurrency_limited_429s_with_no_job_row(
    m_keys, m_plugin, m_rate, m_serializer_cls, m_limiter, m_stage, m_save
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = False

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 429
    assert not m_save.called
    assert not m_stage.called


# ---------------------------------------------------------------------------
# Staging/save failure: the concurrency slot must be released and the
# client gets a user-safe 500 — no leaked exception text, no stuck slot.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_stage_input_failure_releases_slot_and_500s_with_safe_body(
    m_keys, m_plugin, m_rate, m_serializer_cls, m_stage, m_limiter
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = True
    m_stage.side_effect = OSError("object store unreachable: leaked-secret-bucket-key")

    with mock.patch.object(AgentKVJob, "mark_terminal") as m_mark_terminal:
        resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 500
    # The internal exception text must never reach the client.
    assert "leaked-secret-bucket-key" not in str(resp.data)
    assert resp.data["status"] == JobStatus.FAILED.lower()
    assert resp.data["error"] == "Job could not be accepted; nothing was billed."
    assert "job_id" in resp.data

    # stage_input raised before job.save() ever ran: no row exists, so
    # mark_terminal must not be called against a nonexistent job.
    assert not m_mark_terminal.called
    assert m_limiter.release.called
    released_job_id = m_limiter.release.call_args.args[1]
    assert released_job_id == resp.data["job_id"]


# ---------------------------------------------------------------------------
# Happy path: 202 with job_id/status/status_url; staging + dispatch happen;
# job is persisted.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_happy_path_returns_202_with_job_id_status_and_status_url(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_limiter,
    m_stage,
    m_save,
    m_dispatch,
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    def _side_effect(job, *, schema, options):
        job.status = JobStatus.DISPATCHED
        job.dispatched_at = timezone.now()

    m_dispatch.side_effect = _side_effect

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 202
    assert {"job_id", "status", "status_url"} <= set(resp.data.keys())
    # job_id must be a real UUID string.
    uuid.UUID(resp.data["job_id"])
    assert (
        resp.data["status_url"]
        == f"/{settings.AGENT_KV_PATH_PREFIX}/{resp.data['job_id']}"
    )
    assert resp.data["status"] == JobStatus.DISPATCHED.lower()

    assert m_limiter.check_and_acquire.called
    assert m_stage.called
    assert m_save.called
    assert m_dispatch.called


# ---------------------------------------------------------------------------
# The 9-key options dict SubmitView.post builds and forwards to dispatch_job
# must map every field correctly and carry the compiled schema -- a
# dropped/typo'd key here would otherwise pass silently since nothing else
# asserts on dispatch_job's call args.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_dispatch_job_called_with_expected_options_and_schema(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_limiter,
    m_stage,
    m_save,
    m_dispatch,
):
    m_keys.get.return_value = kv_key()
    keys_schema = {"total": {"description": "Grand total"}}
    _mock_serializer(
        m_serializer_cls,
        keys=keys_schema,
        qa=False,
        challenge=False,
        extraction_mode="per-page",
        structured_output=True,
        page_start=2,
        page_end=5,
        document_class="invoice",
        key_notes="ignore footers",
        calculations="annualize rent",
    )
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    ev.SubmitView.as_view()(_authed_post())

    assert m_dispatch.called
    kwargs = m_dispatch.call_args.kwargs
    assert kwargs["schema"] == keys_schema
    assert kwargs["options"] == {
        "qa": False,
        "challenge": False,
        "extraction_mode": "per-page",
        "structured_output": True,
        "page_start": 2,
        "page_end": 5,
        "document_class": "invoice",
        "key_notes": "ignore footers",
        "calculations": "annualize rent",
    }


# ---------------------------------------------------------------------------
# Dispatch failure: job marked FAILED via mark_terminal, concurrency slot
# released, 500 response with a user-safe (non-leaking) error message.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_dispatch_failure_marks_job_failed_releases_slot_and_500s(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_stage,
    m_save,
    m_dispatch,
    m_mark_terminal,
    m_limiter,
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = True
    m_dispatch.side_effect = ev.DispatchError("broker credentials: super-secret-token")

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 500
    # The internal exception text must never reach the client.
    assert "super-secret-token" not in str(resp.data)
    assert resp.data["status"] == JobStatus.FAILED.lower()
    assert "job_id" in resp.data

    assert m_mark_terminal.called
    call = m_mark_terminal.call_args
    assert call.args[2] == JobStatus.FAILED
    assert call.kwargs["error"] == "Job could not be dispatched; nothing was billed."

    assert m_limiter.release.called
    released_job_id = m_limiter.release.call_args.args[1]
    assert released_job_id == str(call.args[0])


# ---------------------------------------------------------------------------
# Belt-and-braces: a raw (non-DispatchError) exception out of dispatch_job
# must get IDENTICAL cleanup to a DispatchError — nothing may escape
# unhandled.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_dispatch_job_raising_non_dispatch_error_is_still_caught_and_cleaned_up(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_stage,
    m_save,
    m_dispatch,
    m_mark_terminal,
    m_limiter,
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = True
    m_dispatch.side_effect = RuntimeError("unexpected: leaked-secret-abc")

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 500
    assert "leaked-secret-abc" not in str(resp.data)
    assert resp.data["status"] == JobStatus.FAILED.lower()
    assert resp.data["error"] == "Job could not be dispatched; nothing was billed."

    assert m_mark_terminal.called
    assert m_mark_terminal.call_args.args[2] == JobStatus.FAILED
    assert m_limiter.release.called


# ---------------------------------------------------------------------------
# End-to-end regression for the widened dispatch.py try: a raw RuntimeError
# from the platform-key lookup deep inside the REAL dispatch_job must still
# result in mark_terminal + release + a safe 500 at the view layer.
# ---------------------------------------------------------------------------
@mock.patch("agent_kv.dispatch._platform_api_key")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_platform_key_lookup_failure_inside_real_dispatch_is_caught_end_to_end(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_stage,
    m_save,
    m_limiter,
    m_mark_terminal,
    m_platform_key,
):
    # ev.dispatch_job is intentionally left real here — only the platform-key
    # lookup deep inside it is mocked to raise, proving the widened
    # dispatch.py try (Fix 2a) plus the view's cleanup (Fix 2b) work together.
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at
    m_platform_key.side_effect = RuntimeError("platform db down: leaked-secret-xyz")

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 500
    assert "leaked-secret-xyz" not in str(resp.data)
    assert resp.data["status"] == JobStatus.FAILED.lower()
    assert resp.data["error"] == "Job could not be dispatched; nothing was billed."

    assert m_mark_terminal.called
    assert m_limiter.release.called


# ---------------------------------------------------------------------------
# timeout=0: the wait branch must never run (no sleep, no polling, no
# attempt to import the Task-9 result_payload module).
# ---------------------------------------------------------------------------
@mock.patch("agent_kv.execution_views.time.sleep")
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_timeout_zero_returns_immediately_without_polling(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_limiter,
    m_stage,
    m_save,
    m_dispatch,
    m_sleep,
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls, timeout=0)
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    with mock.patch.object(AgentKVJob, "refresh_from_db") as m_refresh:
        resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 202
    assert not m_sleep.called
    assert not m_refresh.called


# ---------------------------------------------------------------------------
# Sync-wait regression (spec §7.3 controller ruling on task-9-report.md
# concern 3): if the job fails during the wait window, the inline
# synchronous response must still be a 200 carrying the failure body -- not
# a 404. Before the fix, ``result_payload`` raised ``JobNotFound`` for any
# terminal-but-not-COMPLETED job (blank ``result_ref``), which escaped this
# view as an unhandled 404. Uses the real (unmocked) ``result_payload`` so
# the fix is exercised end-to-end, not just at the unit level.
# ---------------------------------------------------------------------------
@mock.patch("agent_kv.execution_views.time.sleep")
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_sync_wait_returns_200_with_failure_body_when_job_fails_mid_wait(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_limiter,
    m_stage,
    m_save,
    m_dispatch,
    m_sleep,
):
    m_keys.get.return_value = kv_key()
    _mock_serializer(m_serializer_cls, timeout=5)
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    def _refresh_side_effect(job, *args, **kwargs):
        job.status = JobStatus.FAILED
        job.error = "LLM provider timed out"

    with mock.patch.object(
        AgentKVJob, "refresh_from_db", autospec=True, side_effect=_refresh_side_effect
    ):
        resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 200
    assert resp.data == {
        "success": False,
        "status": "failed",
        "error": "LLM provider timed out",
    }
    assert not m_sleep.called


# ---------------------------------------------------------------------------
# Subscription admission (§6.6, following the API deployment path).
#
# Deployments are billed-gated by cloud's SubscriptionMiddleware, which resolves
# the org from the URL (/deployment/api/{org_name}/...). Agent-KV's URL carries
# no org segment -- the org lives in the Bearer key -- so that middleware
# resolves org_id=None for these requests and lets every one of them through.
# The gate is therefore invoked here, after key validation.
# ---------------------------------------------------------------------------
def _key_with_org(slug="acme-slug", pk=42):
    """A key whose FK pk and org slug are deliberately DIFFERENT values.

    `Subscription.organization_id` is a CharField holding the slug; the FK pk is
    an int. Making them differ is what lets the tests below detect the wrong one
    being passed -- with a single shared value the assertion would pass either
    way and the gate could silently never match a subscription row.
    """
    from account_v2.models import Organization  # noqa: PLC0415

    key = AgentKVKey(name="k", is_active=True)
    key.organization = Organization(id=pk, organization_id=slug)
    return key


@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(AgentKVKey, "objects")
def test_subscription_denial_is_returned_verbatim_and_starts_no_work(
    m_keys, m_rate, m_serializer_cls, m_limiter, m_stage, m_save
):
    """A 402 from the gate must reach the client unchanged -- same status and
    body an API deployment returns for the same subscription state -- and must
    stop the request before any billable work, slot or row."""
    from django.http import HttpResponse  # noqa: PLC0415

    m_keys.get.return_value = _key_with_org()
    _mock_serializer(m_serializer_cls)
    denial = HttpResponse(b'{"errors": "Trial period expired."}', status=402)
    gate = mock.Mock()
    gate.check.return_value = denial

    with mock.patch.object(
        ev, "get_plugin", return_value={"module": object(), "service_class": lambda: gate}
    ):
        resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 402
    assert not m_save.called
    assert not m_stage.called
    assert not m_limiter.check_and_acquire.called


@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(AgentKVKey, "objects")
def test_subscription_gate_is_passed_the_org_slug_not_the_fk_pk(
    m_keys, m_rate, m_serializer_cls, m_limiter
):
    """The gate must receive `key.organization.organization_id` (the slug that
    `Subscription.organization_id` is keyed on), NOT `key.organization_id` (the
    Organization FK primary key).

    Passing the pk matches no subscription row, and the shared policy reads "no
    row" as "nothing to enforce" -- so the gate would admit every request while
    looking fully wired. This test is the only thing standing between that
    one-attribute slip and a billing gate that never fires.
    """
    m_keys.get.return_value = _key_with_org(slug="acme-slug", pk=42)
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = False  # stop early; gate already ran
    gate = mock.Mock()
    gate.check.return_value = None

    with mock.patch.object(
        ev, "get_plugin", return_value={"module": object(), "service_class": lambda: gate}
    ):
        ev.SubmitView.as_view()(_authed_post())

    assert gate.check.called
    passed_org = gate.check.call_args.args[0]
    assert passed_org == "acme-slug", f"gate got {passed_org!r}, expected the org slug"
    assert passed_org != 42


@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_plugin_without_a_service_class_still_proceeds(
    m_keys, m_plugin, m_rate, m_serializer_cls, m_limiter
):
    """A cloud build predating the gate exposes no `service_class`. The view
    must degrade to today's behaviour rather than 500 -- the capability probe
    above already 501s an engine-less deployment, so this only covers the
    version skew between an older plugin and a newer backend."""
    m_keys.get.return_value = _key_with_org()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = False

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 429  # reached the concurrency limiter, not a 500


# ---------------------------------------------------------------------------
# Integration: the REAL serializer through the REAL view.
#
# Every other test in this module patches SubmitSerializer and feeds the view a
# `validated_data` built by _valid_validated_data() -- so the view is asserted
# against a shape this file makes up, not the one the serializer actually
# emits. The serializer suite has the mirror-image blind spot: it validates
# payloads and never runs a view. Both pass even if the two disagree, which is
# precisely the seam an extractor-scoped wire format (§7.0) moves.
#
# This test builds a real multipart upload, runs it through the real serializer
# and the real view, and asserts what reaches dispatch_job -- the frozen
# OSS<->cloud contract on the far side.
# ---------------------------------------------------------------------------
def _real_multipart_post(extractors, **job_level):
    import json as _json  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415

    fixture = _os.path.join(_os.path.dirname(__file__), "fixtures", "two_page.pdf")
    with open(fixture, "rb") as fh:
        upload = SimpleUploadedFile("doc.pdf", fh.read(), content_type="application/pdf")
    payload = {"file": upload, "extractors": _json.dumps(extractors), **job_level}
    req = APIRequestFactory().post("/agent-kv/", payload, format="multipart")
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)  # autospec: see _stamp_created_at
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_real_serializer_through_real_view_reaches_dispatch_intact(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch
):
    m_keys.get.return_value = kv_key()
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at
    schema = {"total": {"description": "Grand total"}}

    resp = ev.SubmitView.as_view()(
        _real_multipart_post(
            [{"name": "kv", "keys": schema,
              "options": {"qa": False, "extraction_mode": "per-page"}}],
            page_start=2, page_end=5,
        )
    )

    assert resp.status_code == 202, resp.data
    kwargs = m_dispatch.call_args.kwargs
    # The extractor's own schema is what the engine is asked to extract...
    assert kwargs["schema"] == schema
    # ...its options survive the round trip with defaults filled in...
    assert kwargs["options"]["qa"] is False
    assert kwargs["options"]["extraction_mode"] == "per-page"
    assert kwargs["options"]["challenge"] is True  # untouched default
    # ...and the job-level page range is folded into options, because that is
    # where the engine reads it from (the frozen executor_params contract).
    assert kwargs["options"]["page_start"] == 2
    assert kwargs["options"]["page_end"] == 5


@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value={"module": object()})
@mock.patch.object(AgentKVKey, "objects")
def test_real_serializer_rejects_the_old_flat_shape_with_400(m_keys, m_plugin, m_rate):
    """End-to-end proof of the hard switch: a caller on the pre-§7.0 format gets
    a 400 from the real stack, not a job that quietly ran with defaults."""
    import json as _json  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415

    m_keys.get.return_value = kv_key()
    fixture = _os.path.join(_os.path.dirname(__file__), "fixtures", "two_page.pdf")
    with open(fixture, "rb") as fh:
        upload = SimpleUploadedFile("doc.pdf", fh.read(), content_type="application/pdf")
    req = APIRequestFactory().post(
        "/agent-kv/",
        {"file": upload, "keys": _json.dumps({"total": {"description": "T"}}),
         "qa": "false"},
        format="multipart",
    )
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"

    resp = ev.SubmitView.as_view()(req)

    assert resp.status_code == 400
    assert "extractors" in str(resp.data)
