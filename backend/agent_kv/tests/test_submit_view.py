import os
import uuid
from unittest import mock

import django
import pytest
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


def _plugin_with_gate(denial=None):
    """A plugin dict shaped like the cloud build's, with a gate that admits.

    Every submit test needs one now: a plugin WITHOUT `service_class` means the
    deployment cannot check entitlement, and the view refuses rather than
    dispatching billable work unmetered (see
    `test_plugin_without_a_service_class_is_refused`).
    """
    gate = mock.Mock()
    gate.check.return_value = denial
    return {"module": object(), "service_class": lambda: gate}


def _authed_post(data=None):
    req = _post(data)
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


# Fields describing the REQUEST rather than an extractor (spec §7.1); anything
# else an override names is routed into the kv extractor's options, so each test
# still reads as "submit with this one thing changed".
_JOB_LEVEL = {
    "file",
    "extractors",
    "page_start",
    "page_end",
    "timeout",
    "tags",
    "custom_data",
    "webhook_url",
}


def _valid_validated_data(**overrides):
    """`SubmitSerializer.validated_data` in the extractor-scoped shape (§7.0)."""
    # `table`, not `kv`. The carve-out re-pointed the real-serializer tests and
    # missed this mocked payload, so every view test driven by it called
    # `dispatch_job(extractor="kv")` -- whose FIRST statement is
    # `EXTRACTOR_ROUTES["kv"]`, a KeyError raised OUTSIDE the try. That landed
    # in SubmitView's belt-and-braces `except Exception` and produced the exact
    # 500 some of these tests assert, so they passed while never reaching the
    # code they name. It also meant the whole file exercised the view with an
    # `extractors` payload the real serializer rejects with a 400.
    keys = overrides.pop("keys", {"target_table": "Rent roll"})
    # EXPLICIT, and empty by default. `_resolved_adapters` reads
    # `entry.get("adapters")` and returns early when it is falsy -- a MagicMock
    # auto-attribute here would be TRUTHY, so the gate would fall through to a
    # real `AdapterInstance` query and every view test would die on "Database
    # access not allowed". Tests that exercise the gate set it and mock the
    # lookup; the rest leave it empty and never touch the ORM.
    adapters = overrides.pop("adapters", {})
    options = {
        "instructions": "",
        "json_structure": "",
        "enable_header_mapping": False,
        "correct_number_separators": False,
        "number_format": "US",
    }
    options.update({k: overrides.pop(k) for k in list(overrides) if k not in _JOB_LEVEL})
    data = {
        "file": mock.Mock(name="uploaded_file"),
        "extractors": [
            {"name": "table", "keys": keys, "adapters": adapters, "options": options}
        ],
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


#: A `table` submit's three required adapter roles.
_TABLE_ADAPTERS = {
    "llm": "11111111-1111-1111-1111-111111111111",
    "lite_llm": "22222222-2222-2222-2222-222222222222",
    "x2text": "33333333-3333-3333-3333-333333333333",
}

#: Which `AdapterTypes` value each role must resolve to.
_ROLE_TYPES = {"llm": "LLM", "lite_llm": "LLM", "x2text": "X2TEXT"}


def _adapters_owned_by(
    organization_id, *, types=None, missing=(), unusable=(), unavailable=()
):
    """Patch the single-adapter lookup `_resolved_adapters` performs.

    Patches `ev._lookup_adapter`, the view's own seam, rather than the ORM.
    Two reasons, both learned the hard way: `AdapterInstance._base_manager` is
    a read-only property and cannot be patched at all, and patching `.objects`
    is what hid the defect where the gate refused every valid submit (that
    manager auto-filters by a request-local org this route never sets).

    So these tests assert the GATE's logic -- org match, type match, identical
    refusals -- and `tests/test_adapter_scoping.py` asserts that the real
    lookup finds a real adapter with no request context. Neither covers the
    other.

    An id in `missing` resolves to None (not this org's, or nonexistent -- the
    gate cannot and must not tell those apart); everything else resolves to an
    adapter of the type `types` gives, defaulting to the right one per role.
    `unusable` / `unavailable` flip `is_usable` / `is_available` for the ids
    named, which is how the trial-exhaustion and deprecation refusals are
    reached here.

    Both flags are set EXPLICITLY on every stand-in, never left to `Mock`'s
    auto-attribute. A bare `mock.Mock()` returns a truthy child for any
    attribute, so a gate that reads `adapter.is_usable` would be satisfied by a
    mock that was never asked to model it -- the gate could be deleted and
    these tests would still pass. The real values live in
    `tests/test_adapter_scoping.py`, against rows the DB defaulted itself.
    """
    type_by_id = {
        aid: (types or {}).get(role, _ROLE_TYPES[role])
        for role, aid in _TABLE_ADAPTERS.items()
    }
    missing_ids = {str(m) for m in missing}
    unusable_ids = {str(m) for m in unusable}
    unavailable_ids = {str(m) for m in unavailable}

    def _lookup(adapter_id, org_id):
        aid = str(adapter_id)
        if aid in missing_ids or org_id != organization_id:
            return None
        return mock.Mock(
            id=aid,
            adapter_type=type_by_id.get(aid, "LLM"),
            is_usable=aid not in unusable_ids,
            is_available=aid not in unavailable_ids,
        )

    return mock.patch.object(ev, "_lookup_adapter", side_effect=_lookup)


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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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

    def _side_effect(job, *, extractor, schema, options, adapters=None):
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
# must map every field correctly -- a dropped/typo'd key here would otherwise
# pass silently since nothing else asserts on dispatch_job's call args.
#
# It carries the RAW `keys` dict, not a `CompiledSchema`. The serializer used
# to stash the compiled form and nothing read it; the engine recompiles from
# the raw dict by design (see `compile.py`'s docstring), and the compiled form
# could not cross the queue anyway.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input", return_value="org/o/agent_kv/j/input.pdf")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
    keys_schema = {"target_table": "Rent roll"}
    _mock_serializer(
        m_serializer_cls,
        keys=keys_schema,
        number_format="EU",
        enable_header_mapping=True,
        instructions="skip the header row",
        page_start=2,
        page_end=5,
    )
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    ev.SubmitView.as_view()(_authed_post())

    assert m_dispatch.called
    kwargs = m_dispatch.call_args.kwargs
    # The extractor name itself was never asserted, so this test could not tell
    # a `table` dispatch from a `kv` one -- which is how the mocked payload
    # stayed on `kv` right through the carve-out.
    assert kwargs["extractor"] == "table"
    assert kwargs["schema"] == keys_schema
    assert kwargs["options"] == {
        "instructions": "skip the header row",
        "json_structure": "",
        "enable_header_mapping": True,
        "correct_number_separators": False,
        "number_format": "EU",
        "page_start": 2,
        "page_end": 5,
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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

    # The assertion this test was missing. Without it it passed while never
    # reaching the code it names: the mocked payload said `kv`, so
    # `dispatch_job`'s first statement -- `EXTRACTOR_ROUTES["kv"]` -- raised a
    # KeyError OUTSIDE the try, the view's belt-and-braces handler produced the
    # same 500, and `_platform_api_key` was never called. The
    # "leaked-secret-xyz" check below was vacuous: that string was never
    # produced.
    assert m_platform_key.called, (
        "the platform-key lookup was never reached, so this test proves "
        "nothing about the widened dispatch.py try it exists to cover"
    )

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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
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
    stop the request before any billable work, slot or row.
    """
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
def test_plugin_without_a_service_class_is_refused(
    m_keys, m_plugin, m_rate, m_serializer_cls, m_limiter
):
    """A plugin that exposes no `service_class` cannot check entitlement, so
    the submit is REFUSED rather than admitted.

    This used to degrade to "proceed", to tolerate a cloud image predating the
    gate. But the admitted request dispatches billable LLM and OCR work, and
    this route's URL carries no org segment, so `SubscriptionMiddleware` cannot
    catch it downstream either -- a mixed deploy would run unmetered paid work
    with nothing anywhere enforcing entitlement. Reported by Greptile on #2317.

    503, not 402: the subscription was never evaluated, so reporting it as
    denied would send an operator to the billing system for what is an
    image-pairing problem.
    """
    m_keys.get.return_value = _key_with_org()
    _mock_serializer(m_serializer_cls)
    m_limiter.check_and_acquire.return_value = False

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 503, resp.data
    # Refused BEFORE a slot was taken or anything was staged.
    assert not m_limiter.check_and_acquire.called


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
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_real_serializer_through_real_view_reaches_dispatch_intact_for_table(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch
):
    """The table path's version of the test above -- and the exact contract
    that already broke once: an earlier version had the consumer reading
    `target_table` off the top level of `executor_params` while the producer
    nested it under `schema`, which would have failed every table job, and it
    survived two rounds of unit tests on both sides because each side was
    internally consistent on its own. Only a test that runs the real
    serializer AND the real view together, and inspects what lands at
    `dispatch_job`, can catch that kind of drift.
    """
    m_keys.get.return_value = kv_key()
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at
    schema = {"target_table": "Rent rolls"}

    with _adapters_owned_by(kv_key().organization_id):
        resp = ev.SubmitView.as_view()(
            _real_multipart_post(
                [
                    {
                        "name": "table",
                        "keys": schema,
                        "adapters": _TABLE_ADAPTERS,
                        "options": {"instructions": "skip totals"},
                    }
                ],
            )
        )

    assert resp.status_code == 202, resp.data
    kwargs = m_dispatch.call_args.kwargs
    assert kwargs["extractor"] == "table"
    # The caller's own adapter instances reach the executor, by role. This is
    # the whole point of the adapter wire format: the engine resolves these
    # through the platform service instead of reading operator env vars.
    assert kwargs["adapters"] == _TABLE_ADAPTERS
    # Nested under `schema`, matching exactly what the cloud executor reads
    # (`params["schema"]["target_table"]") -- NOT hoisted to the top level.
    assert kwargs["schema"] == {"target_table": "Rent rolls"}
    assert kwargs["options"]["instructions"] == "skip totals"

    # The job row records which extractor it ran (execution_views.py:142) --
    # asserted here since nothing else in this suite reads it back.
    job = m_dispatch.call_args.args[0]
    assert job.extractor == "table"


@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_real_serializer_rejects_the_old_flat_shape_with_400(m_keys, m_plugin, m_rate):
    """End-to-end proof of the hard switch: a caller on the pre-§7.0 format gets
    a 400 from the real stack, not a job that quietly ran with defaults.
    """
    import json as _json  # noqa: PLC0415
    import os as _os  # noqa: PLC0415

    from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: PLC0415

    m_keys.get.return_value = kv_key()
    fixture = _os.path.join(_os.path.dirname(__file__), "fixtures", "two_page.pdf")
    with open(fixture, "rb") as fh:
        upload = SimpleUploadedFile("doc.pdf", fh.read(), content_type="application/pdf")
    req = APIRequestFactory().post(
        "/agent-kv/",
        {
            "file": upload,
            "keys": _json.dumps({"total": {"description": "T"}}),
            "qa": "false",
        },
        format="multipart",
    )
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"

    resp = ev.SubmitView.as_view()(req)

    assert resp.status_code == 400
    assert "extractors" in str(resp.data)


# ---------------------------------------------------------------------------
# (9) The `extractors` file part is read under a bound, and decoded strictly.
#
# The size cap lives in `validate_extractors`, i.e. AFTER the part was
# materialised, and `DATA_UPLOAD_MAX_MEMORY_SIZE` excludes file-typed parts --
# so a 500 MB part was read in full before being rejected at 256 KiB. One such
# request per worker process OOMs the pod: a cheap denial of service.
#
# Reported as 2.7 in the branch review.
# ---------------------------------------------------------------------------
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402


@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_an_oversized_extractors_part_is_rejected_by_size(m_keys, m_plugin, m_rate):
    """The cap is now consulted BEFORE the part is materialised.

    Note what this does and does not prove: it pins the 400, which is the
    behaviour a caller sees. It cannot observe the read size, because the
    multipart parser builds its own file object from the wire and the instance
    constructed here never reaches the view. The bounded read itself is visible
    in `SubmitView.post` as `part.read(limit + 1)`; a test that claimed to
    verify it through this path would be asserting on an object the view never
    touched.
    """
    m_keys.get.return_value = _key_with_org()
    cap = 64
    part = SimpleUploadedFile("extractors.json", b"x" * (cap * 50))

    req = APIRequestFactory().post("/agent-kv/", {"extractors": part}, format="multipart")
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    with mock.patch.object(ev.settings, "AGENT_KV_MAX_SCHEMA_BYTES", cap):
        resp = ev.SubmitView.as_view()(req)

    assert resp.status_code == 400
    assert "exceeds" in str(resp.data)


@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_a_non_utf8_extractors_part_is_rejected(m_keys, m_plugin, m_rate):
    """`errors="replace"` let a latin-1 key name decode to U+FFFD and then
    compile cleanly -- a malformed payload became a job that ran against a
    schema the caller never wrote.
    """
    m_keys.get.return_value = _key_with_org()

    class _Latin1Part:
        def read(self, n=-1):
            return b'[{"name": "table", "keys": {"target_table": "\xe9"}}]'

    req = APIRequestFactory().post(
        "/agent-kv/", {"extractors": _Latin1Part()}, format="multipart"
    )
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    resp = ev.SubmitView.as_view()(req)

    assert resp.status_code == 400
    assert "UTF-8" in str(resp.data)


# ---------------------------------------------------------------------------
# (10) A DB failure after staging must not orphan the upload.
#
# `run_ttl_cleanup` selects candidates from AgentKVJob rows, so an object whose
# row was never saved is unreachable by every cleanup path there is -- customer
# data sitting in the bucket that nobody can find or delete.
#
# Reported as 2.8 in the branch review.
# ---------------------------------------------------------------------------
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "check_and_acquire", return_value=True)
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "save", side_effect=RuntimeError("db down"))
@mock.patch.object(ev, "stage_input", return_value="org1/job/in.pdf")
@mock.patch.object(ev, "SubmitSerializer")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_a_save_failure_after_staging_removes_the_staged_object(
    m_keys,
    m_plugin,
    m_rate,
    m_serializer_cls,
    m_stage,
    m_save,
    m_mark_terminal,
    m_acquire,
    m_release,
    m_delete,
):
    m_keys.get.return_value = _key_with_org()
    _mock_serializer(m_serializer_cls)

    resp = ev.SubmitView.as_view()(_authed_post())

    assert resp.status_code == 500
    assert m_delete.called, (
        "the staged upload was left in the bucket with no job row carrying its "
        "ref; TTL cleanup selects from job rows, so it can never be reached"
    )


# ---------------------------------------------------------------------------
# The adapter tenancy gate.
#
# `POST /agent-kv/` names platform adapters by id. The platform service DOES
# re-scope its lookups by organization (`WHERE id=%s and organization_id=%s`,
# against the org of the job's own platform key), so this gate is defence in
# depth rather than the only thing standing between a caller and another
# tenant's credential -- the comment here previously claimed the latter.
#
# It is still load-bearing for what the platform service does not do: produce a
# 400 at submit naming the role (instead of an `SdkError` mid-run, after a slot
# and staging are spent), and refuse an exhausted trial (`is_usable`) or a
# deprecated adapter (`is_available`), neither of which the platform service
# checks before handing the credentials back.
# ---------------------------------------------------------------------------


@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
@pytest.mark.parametrize("stolen_role", ["llm", "lite_llm", "x2text"])
def test_an_adapter_from_another_org_is_refused(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch, stolen_role
):
    """Parametrised across all three roles: one unguarded slot is enough."""
    key = kv_key()
    m_keys.get.return_value = key
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    with _adapters_owned_by(
        key.organization_id, missing=[_TABLE_ADAPTERS[stolen_role]]
    ):
        resp = ev.SubmitView.as_view()(
            _real_multipart_post(
                [
                    {
                        "name": "table",
                        "keys": {"target_table": "Rent rolls"},
                        "adapters": _TABLE_ADAPTERS,
                        "options": {},
                    }
                ],
            )
        )

    assert resp.status_code == 400, resp.data
    assert "no such adapter in this organization" in str(resp.data)
    assert stolen_role in str(resp.data)
    assert not m_dispatch.called, "an unowned adapter must never reach the executor"
    assert not m_stage.called, "and nothing may be staged or billed first"


@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_an_adapter_of_the_wrong_type_is_refused(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch
):
    """An X2TEXT id in the `llm` slot resolves fine and then fails deep inside
    the engine as a provider error -- which reads like a broken model rather
    than two swapped UUIDs. Caught at submit instead.
    """
    key = kv_key()
    m_keys.get.return_value = key
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    with _adapters_owned_by(key.organization_id, types={"llm": "X2TEXT"}):
        resp = ev.SubmitView.as_view()(
            _real_multipart_post(
                [
                    {
                        "name": "table",
                        "keys": {"target_table": "Rent rolls"},
                        "adapters": _TABLE_ADAPTERS,
                        "options": {},
                    }
                ],
            )
        )

    assert resp.status_code == 400, resp.data
    assert "expected 'LLM'" in str(resp.data)
    assert not m_dispatch.called


@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_an_exhausted_trial_adapter_is_refused_before_anything_is_billed(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch
):
    """`is_usable=False` must 400, not 202.

    A frictionlessly onboarded org runs on operator-funded sample credentials;
    billing flips `is_usable` when the free allowance is gone, and the IDE,
    workflows and Prompt Studio all refuse from that moment. The platform
    service does NOT check the flag -- it hands the credentials back -- so if
    this endpoint does not check it either, the submit is accepted and the
    OPERATOR pays for the caller's extraction.
    """
    key = kv_key()
    m_keys.get.return_value = key
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    with _adapters_owned_by(key.organization_id, unusable=[_TABLE_ADAPTERS["llm"]]):
        resp = ev.SubmitView.as_view()(
            _real_multipart_post(
                [
                    {
                        "name": "table",
                        "keys": {"target_table": "Rent rolls"},
                        "adapters": _TABLE_ADAPTERS,
                        "options": {},
                    }
                ],
            )
        )

    assert resp.status_code == 400
    assert "exhausted" in str(resp.data), resp.data
    assert not m_dispatch.called, "an exhausted trial must not reach the executor"
    assert not m_stage.called, "nor be charged for staging the upload"


@mock.patch.object(ev, "dispatch_job")
@mock.patch.object(AgentKVJob, "save", autospec=True)
@mock.patch.object(ev, "stage_input")
@mock.patch.object(ev, "AgentKVConcurrencyLimiter")
@mock.patch.object(ev, "check_key_rate", return_value=True)
@mock.patch.object(ev, "get_plugin", return_value=_plugin_with_gate())
@mock.patch.object(AgentKVKey, "objects")
def test_a_deprecated_adapter_is_refused_at_submit(
    m_keys, m_plugin, m_rate, m_limiter, m_stage, m_save, m_dispatch
):
    """`is_available=False` means the SDK registry no longer carries it.

    Left to the executor this raises `InValidAdapterId` deep in the engine and
    reaches the caller as a mid-run extraction failure, on a job that already
    took a slot and billed for staging.
    """
    key = kv_key()
    m_keys.get.return_value = key
    m_limiter.check_and_acquire.return_value = True
    m_save.side_effect = _stamp_created_at

    with _adapters_owned_by(
        key.organization_id, unavailable=[_TABLE_ADAPTERS["x2text"]]
    ):
        resp = ev.SubmitView.as_view()(
            _real_multipart_post(
                [
                    {
                        "name": "table",
                        "keys": {"target_table": "Rent rolls"},
                        "adapters": _TABLE_ADAPTERS,
                        "options": {},
                    }
                ],
            )
        )

    assert resp.status_code == 400
    assert "deprecated" in str(resp.data), resp.data
    assert not m_dispatch.called
    assert not m_stage.called
