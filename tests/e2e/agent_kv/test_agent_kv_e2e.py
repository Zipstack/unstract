"""E2E: the Agent-KV product API against a real running platform.

This lane needs the cloud ``agentic_kv`` executor plugin (docs/agent-kv-api.md
§11) -- an OSS-only deployment 501s every submit, so it is NOT part of a plain
OSS e2e sweep. The whole module skips unless both:

- ``UNSTRACT_BACKEND_URL`` is set (the usual e2e platform-URL gate every
  other lane in this tree relies on), AND
- ``AGENT_KV_E2E=1`` is set explicitly -- so this lane never runs by
  accident just because a platform happens to be up; it must be opted into
  for a run that actually ships the plugin.

A second, narrower gate (the ``require_llm`` fixture below) applies only to
the two scenarios whose assertions depend on a job actually reaching
COMPLETED (real extraction happened): either ``AGENT_KV_LLM_API_KEY`` or
``UNSTRACT_LLM_MOCK_RESPONSE`` must be set. Every other scenario here is
gated purely by request-time checks (auth, schema compile, the concurrency
limiter, the pre-OCR page cap) that resolve before any LLM call, so they
don't need either.

Values extracted under ``UNSTRACT_LLM_MOCK_RESPONSE`` are whatever the mock
config returns, not real answers -- assertions here deliberately check
*structure* (the requested keys are present) rather than field values, for
both the mock and a real-key run, to keep this lane's outcome independent of
model behavior.

Test order matters: the concurrency scenario is deliberately defined LAST
(see its own docstring) and ``tests/groups.yaml``'s ``e2e-agent-kv`` entry
pins ``parallel: false`` for the same reason -- see that scenario for why.

**A third, operator-driven gate: ``AGENT_KV_E2E_BAD_KEY_JOB=1``.** One
scenario here (``test_bad_llm_key_ends_failed``) needs a *dispatched* job to
end FAILED, which no request-time check can produce -- the only deterministic
way to get there is to run the platform with a deliberately invalid
``AGENT_KV_LLM_API_KEY`` so the executor's LLM calls all fail. That is a
whole-stack configuration, not something a test can arrange, so the scenario
skips unless an operator sets ``AGENT_KV_E2E_BAD_KEY_JOB=1`` to declare "this
stack is running with a bad Agent-KV LLM key on purpose". Note that every
other scenario in this module that needs a job to COMPLETE will (correctly)
fail on such a stack -- run this one on its own, e.g.::

    AGENT_KV_E2E=1 AGENT_KV_E2E_BAD_KEY_JOB=1 pytest tests/e2e/agent_kv -k bad_llm_key

What it asserts is the *shape* of the failure, not its text: the job reaches
``failed`` and the ``error`` the customer sees is user-safe -- no filesystem
paths, no ``Permission denied``, no provider response body (spec Sec 8's
``"<stage> failed: <class>"`` contract).
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import time

import pytest
import requests

from tests.e2e.agent_kv.conftest import (
    INVOICE_PDF,
    INVOICE_XLSX,
    RENT_ROLL_PDF,
    AgentKVAuth,
    cancel,
    delete,
    poll,
    result,
    submit,
    submit_raw,
    table_keys,
    table_result_body,
    table_stages,
)

if not (os.environ.get("UNSTRACT_BACKEND_URL") and os.environ.get("AGENT_KV_E2E") == "1"):
    pytest.skip(
        "agent-kv e2e lane needs UNSTRACT_BACKEND_URL and AGENT_KV_E2E=1 "
        "(this lane requires the cloud agentic_kv executor plugin -- see "
        "docs/agent-kv-api.md §11)",
        allow_module_level=True,
    )

pytestmark = [pytest.mark.e2e]

_INVOICE_BYTES = INVOICE_PDF.read_bytes()
_RENT_ROLL_BYTES = RENT_ROLL_PDF.read_bytes()

# Bounded wait for the org's concurrency slots to free up again. Used by the
# cancel scenario (a cancelled job must not leak its slot) and by the
# concurrency scenario's own cleanup.
_SLOT_DRAIN_TIMEOUT_S = 120
_SLOT_DRAIN_POLL_INTERVAL_S = 3


def _validation_error_attrs(body: object) -> set[str]:
    """The field names a 400 body blames, across BOTH error envelopes.

    This lane runs against whichever deployment is up, and the two differ:

    - OSS DRF default -- ``{"file": ["Unreadable PDF"]}``: the field names are
      the top-level keys.
    - Cloud (``drf-standardized-errors``) --
      ``{"type": "validation_error", "errors": [{"code": "invalid",
      "detail": "Unreadable PDF", "attr": "file"}]}``: the field names are the
      ``attr`` of each entry under ``errors``.

    Returns an empty set for anything that is neither shape, so a caller's
    ``assert "file" in _validation_error_attrs(body), body`` fails loudly with
    the real body rather than raising a ``KeyError``/``TypeError``.
    """
    if not isinstance(body, dict):
        return set()
    errors = body.get("errors")
    if isinstance(errors, list):
        return {
            entry["attr"]
            for entry in errors
            if isinstance(entry, dict) and isinstance(entry.get("attr"), str)
        }
    return {key for key in body if isinstance(key, str)}


def _cheap_submit(auth: AgentKVAuth) -> requests.Response:
    """One raw submit with QA and challenge off -- the cheapest job this API
    will accept, used purely to occupy/probe a concurrency slot.
    """
    return submit_raw(
        auth,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
    )


def _drain_until_slot_free(
    auth: AgentKVAuth, timeout_s: float = _SLOT_DRAIN_TIMEOUT_S
) -> bool:
    """Probe with cheap submits until one is ACCEPTED (proof a slot is free)
    or the bounded wait runs out. Any accepted probe is cancelled again so it
    doesn't hold the slot it just proved was available.

    Returns True if a probe was accepted, False if the window expired or the
    probes stopped being answerable. Never raises -- callers decide whether a
    False is an assertion failure (the cancel scenario) or merely a
    best-effort cleanup giving up (the concurrency scenario).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            probe = _cheap_submit(auth)
        except Exception:  # noqa: BLE001 - probing only
            return False
        if probe.status_code == 202:
            try:
                cancel(auth, probe.json()["job_id"])
            except Exception:  # noqa: BLE001 - cleanup only
                pass
            return True
        time.sleep(_SLOT_DRAIN_POLL_INTERVAL_S)
    return False


@pytest.fixture
def require_llm() -> None:
    """Skip a scenario that needs a job to actually reach COMPLETED.

    Every other scenario in this module resolves before any LLM call
    (auth/schema/limiter/page-cap checks); only the two that poll a job all
    the way to a genuine COMPLETED result need this.
    """
    has_key = os.environ.get("AGENT_KV_LLM_API_KEY")
    has_mock = os.environ.get("UNSTRACT_LLM_MOCK_RESPONSE")
    if not (has_key or has_mock):
        pytest.skip(
            "needs AGENT_KV_LLM_API_KEY or UNSTRACT_LLM_MOCK_RESPONSE so the "
            "job can actually reach COMPLETED"
        )


# ---------------------------------------------------------------------------
# 1. Auth
# ---------------------------------------------------------------------------


def test_submit_without_key_is_403(agent_kv_key: AgentKVAuth) -> None:
    resp = requests.post(
        agent_kv_key.exec_url,
        files={"file": ("invoice.pdf", _INVOICE_BYTES, "application/pdf")},
        data={"keys": '{"total": {"description": "Grand total"}}'},
        timeout=30,
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 2. Validate
# ---------------------------------------------------------------------------


def test_table_extractor_happy_path(agent_kv_key: AgentKVAuth, require_llm: None) -> None:
    """A `table` entry runs the table engine and files its result under `table`.

    Before the job row recorded its extractor, every response keyed by the
    hardcoded `kv` name -- a table job's output would have been filed under the
    wrong extractor, which no unit test on either side would have caught.
    """
    job_id, status_url = submit(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
        extractor="table",
    )
    assert status_url.endswith(job_id), status_url

    status_doc = poll(agent_kv_key, job_id, timeout_s=600)
    assert status_doc["status"] == "completed", status_doc
    # Keyed by the extractor that ran, and by that one only.
    assert set(status_doc["extractors"]) == {"table"}, status_doc

    # R7: the stage is recorded AND visible. StageReportView persists whatever
    # name the executor sends, so a KV-only stage-name filter would leave this
    # list empty while the job still completed.
    stages = {s["name"]: s for s in table_stages(status_doc)}
    assert "table_extraction" in stages, table_stages(status_doc)
    assert stages["table_extraction"]["status"] == "done", stages

    resp = result(agent_kv_key, job_id)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["success"] is True, payload
    assert payload["status"] == "completed", payload

    body = table_result_body(resp)
    # Structure, not values: this lane runs under a mock LLM as well as a real
    # key, so field values are not assertable (see the module docstring).
    assert isinstance(body["tables"], list), body
    assert "page_count" in body, body
    assert "row_count" in body, body

    assert set(payload["usage_summary"]["by_extractor"]) == {"table"}, payload

    # Re-readable until TTL (D11), same contract as the kv path.
    again = result(agent_kv_key, job_id)
    assert again.status_code == 200, again.text
    assert again.json() == payload, "result must be stable on re-read"


def test_table_entry_without_a_target_table_is_400(agent_kv_key: AgentKVAuth) -> None:
    """Rejected at submit, before any paid work -- `target_table` is the
    engine's one required extraction parameter.
    """
    resp = submit_raw(
        agent_kv_key, _RENT_ROLL_BYTES, "rent_roll.pdf", {}, extractor="table"
    )
    assert resp.status_code == 400, resp.text
    assert "target_table" in resp.text, resp.text


def test_a_kv_option_on_a_table_entry_is_400(agent_kv_key: AgentKVAuth) -> None:
    """Per-extractor options exist so an option aimed at the wrong extractor
    cannot be silently dropped and change what the caller is billed for.
    """
    resp = submit_raw(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
        extractor="table",
        qa=True,
    )
    assert resp.status_code == 400, resp.text
    assert "qa" in resp.text, resp.text


def test_an_unknown_extractor_is_400(agent_kv_key: AgentKVAuth) -> None:
    resp = submit_raw(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
        extractor="nonexistent",
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# 4. Failure body (submit-time rejection)
# ---------------------------------------------------------------------------


def test_submit_unreadable_pdf_is_400(agent_kv_key: AgentKVAuth) -> None:
    """A ``.pdf``-named file that isn't a real PDF is rejected before dispatch.

    This is the submit-serializer's own page-count check
    (``pdfplumber.open()`` raising -> ``{"file": "Unreadable PDF"}``), which
    is deterministic and needs no LLM/engine work to reach. The executor's
    own FAILED-terminal path (a job that *dispatches* successfully but the
    engine later fails) has no deterministic trigger reachable without a
    real key/schema combination that's guaranteed to fail -- that path is
    covered by the unit suites instead (e.g.
    ``backend/agent_kv/tests/test_job_views.py``,
    ``backend/agent_kv/tests/test_dispatch.py``).
    """
    garbage = b"this is not a pdf file, just garbage bytes" * 20
    resp = submit_raw(agent_kv_key, garbage, "garbage.pdf", table_keys())
    assert resp.status_code == 400, (
        f"expected 400 (a 501 here means the agent-kv engine plugin isn't "
        f"installed on this deployment): {resp.text}"
    )
    body = resp.json()
    assert "file" in _validation_error_attrs(body), body


# ---------------------------------------------------------------------------
# 5. Cancel
# ---------------------------------------------------------------------------


def test_cancel_mid_run(agent_kv_key: AgentKVAuth) -> None:
    job_id, _ = submit(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
    )
    cancel_resp = cancel(agent_kv_key, job_id)
    # Either cancel won the race (200) or the job was already terminal by the
    # time it landed (409) -- both are correct per docs §7; either way the
    # status endpoint must agree with what cancel just reported.
    assert cancel_resp.status_code in (200, 409), cancel_resp.text
    cancel_body = cancel_resp.json()

    status_resp = requests.get(
        agent_kv_key.job_url(job_id), headers=agent_kv_key.headers, timeout=30
    )
    assert status_resp.status_code == 200, status_resp.text
    final_status = status_resp.json()["status"]  # lowercased, per docs §4

    if cancel_resp.status_code == 200:
        assert cancel_body == {"status": "cancelled"}, cancel_body
        assert final_status == "cancelled", status_resp.json()
    else:
        # Lowercased, like every other status field in this API. The docs and
        # this assertion both used to claim the 409 body carried the RAW
        # uppercase enum -- it does not: `JobCancelView` returns
        # `job.status.lower()`, and the unit test the docs cited as proof
        # (`test_cancel_on_completed_is_409_and_result_untouched`) asserts
        # `{"status": "completed"}`. This lane had never run, so the wrong
        # assertion was never executed. (2.6 in the branch review.)
        assert cancel_body["status"] == final_status, (cancel_body, final_status)


def test_cancelled_job_does_not_leak_its_concurrency_slot(
    agent_kv_key: AgentKVAuth,
) -> None:
    """A cancelled job must give its concurrency slot back.

    ``JobCancelView`` marks the job ``CANCELLED`` directly and never touches
    ``AgentKVConcurrencyLimiter``; the slot is released by the job's own
    *finalize* call, in a ``finally`` (docs/agent-kv-api.md §11a). So the
    release is asynchronous -- it lands whenever the executor that picked the
    job up notices the cancellation and calls back -- which is exactly the
    kind of path where a leak hides: nothing in the cancel request itself
    would fail if the release were dropped, and the only other backstop is
    the limiter's 6-hour slot TTL.

    This is a bounded probe, not a saturation test: it proves the limiter is
    still handing out slots after a cancel (i.e. a cancel cannot wedge it),
    and it reuses the same drain helper the concurrency scenario ends with.
    It deliberately does NOT saturate the org first -- doing so here would
    make every scenario defined after it flaky, which is why the one
    saturating scenario in this module is defined last. The saturated form of
    this check is that last scenario's own drain.
    """
    job_id, _ = submit(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
    )
    cancel_resp = cancel(agent_kv_key, job_id)
    assert cancel_resp.status_code in (200, 409), cancel_resp.text

    assert _drain_until_slot_free(agent_kv_key), (
        f"no submit was accepted within {_SLOT_DRAIN_TIMEOUT_S}s of cancelling "
        f"job {job_id}; the limiter is refusing new work, which means a slot "
        f"was leaked rather than released by finalize"
    )


# ---------------------------------------------------------------------------
# 6. Delete
# ---------------------------------------------------------------------------


def test_delete_completed_job_then_result_404(
    agent_kv_key: AgentKVAuth, require_llm: None
) -> None:
    job_id, _ = submit(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
    )
    status_doc = poll(agent_kv_key, job_id, timeout_s=600)
    assert status_doc["status"] == "completed", status_doc

    del_resp = delete(agent_kv_key, job_id)
    assert del_resp.status_code == 204, del_resp.text

    after = result(agent_kv_key, job_id)
    assert after.status_code == 404, after.text


# ---------------------------------------------------------------------------
# 7. Page cap
# ---------------------------------------------------------------------------


def test_page_cap_rejects_oversized_document(agent_kv_key: AgentKVAuth) -> None:
    fixture_pages = 2  # fixtures/invoice.pdf
    cap_raw = os.environ.get("AGENT_KV_MAX_PAGES")
    if cap_raw is None or int(cap_raw) > fixture_pages:
        pytest.skip(
            f"AGENT_KV_MAX_PAGES={cap_raw!r} exceeds the fixture's "
            f"{fixture_pages} pages; set AGENT_KV_MAX_PAGES<={fixture_pages} "
            "on the backend service to exercise the cap"
        )
    resp = submit_raw(agent_kv_key, _RENT_ROLL_BYTES, "rent_roll.pdf", table_keys())
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "file" in _validation_error_attrs(body), body


# ---------------------------------------------------------------------------
# 8. Executor-side failure (operator-configured bad LLM key)
# ---------------------------------------------------------------------------


def _assert_user_safe_error(error: str) -> None:
    """No internals in a customer-visible error string (spec §8)."""
    lowered = error.lower()
    for leak in ("permission denied", "traceback", "errno", "sk-", "api_key"):
        assert leak not in lowered, f"internal detail {leak!r} leaked into: {error!r}"
    # No filesystem paths: the engine's own text used to carry the executor's
    # tempfile/page-image directories verbatim.
    for leak in ("/app/", "/tmp/", "/var/", "storage/processing", "\\"):
        assert leak not in error, f"a filesystem path leaked into: {error!r}"


def test_bad_llm_key_ends_failed(agent_kv_key: AgentKVAuth) -> None:
    """A job that DISPATCHES and then fails in the executor ends ``failed``
    with a user-safe error.

    Every other failure scenario in this module is a request-time rejection
    (400/403/429) that never reaches the engine. This one covers the other
    half of the contract -- the terminal FAILED path -- and it needs the whole
    stack to be running with a deliberately invalid ``AGENT_KV_LLM_API_KEY``,
    which no test can arrange for itself. Hence the explicit operator gate
    (see the module docstring for how to run it).

    The assertion is about SHAPE, not text: whatever went wrong inside the
    engine, the customer-visible ``error`` must not carry a filesystem path, a
    ``Permission denied``, or a provider response body -- spec §8 mandates the
    user-safe ``"<stage> failed: <class>"`` form (or one of the fixed strings
    ``cancelled`` / ``timed out``), which is what the executor now builds from
    the node listener's exception rather than echoing the engine's own text.
    """
    if os.environ.get("AGENT_KV_E2E_BAD_KEY_JOB") != "1":
        pytest.skip(
            "needs a platform deliberately configured with an INVALID "
            "AGENT_KV_LLM_API_KEY; set AGENT_KV_E2E_BAD_KEY_JOB=1 to declare "
            "that this stack is running that way (see the module docstring)"
        )

    job_id, _ = submit(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
    )

    status_doc = poll(agent_kv_key, job_id, timeout_s=600)
    assert status_doc["status"] == "failed", status_doc
    assert "error" in status_doc, status_doc
    error = status_doc["error"]
    assert isinstance(error, str), status_doc
    assert error, status_doc

    _assert_user_safe_error(error)

    # The result endpoint reports the same failure, in the docs §5 shape.
    resp = result(agent_kv_key, job_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False, body
    assert body["status"] == "failed", body
    _assert_user_safe_error(body["error"])


# ---------------------------------------------------------------------------
# 9. Document cache (spec §6.5 document tier)
# ---------------------------------------------------------------------------


def test_sync_wait_submit_returns_result_inline(
    agent_kv_key: AgentKVAuth, require_llm: None
) -> None:
    """A submit with ``timeout`` seconds sync-waits: if the job reaches a
    terminal state inside the window, the response is 200 with the result
    payload itself (docs §3) -- no polling leg. Uses the same invoice as the
    happy path, so a warm document cache keeps the wait well inside the
    window; even a cold cache (~15 s pipeline) fits comfortably.
    """
    resp = submit_raw(
        agent_kv_key,
        _RENT_ROLL_BYTES,
        "rent_roll.pdf",
        table_keys(),
        timeout=120,
    )
    assert resp.status_code == 200, (
        f"sync-wait submit: HTTP {resp.status_code} (expected 200 with the "
        f"inline result): {resp.text}"
    )
    body = resp.json()
    # `success`/`status` are top level on every terminal payload; the engine's
    # own record is namespaced per extractor (spec §7.3).
    assert body.get("success") is True, body
    body = table_result_body(resp)
    assert isinstance(body["tables"], list), body
    assert "row_count" in body, body


# ---------------------------------------------------------------------------
# 9c. Excel input
# ---------------------------------------------------------------------------


def test_excel_submit_extracts(agent_kv_key: AgentKVAuth, require_llm: None) -> None:
    """An .xlsx submit runs the whole pipeline. Excel has no pre-OCR page
    count (``pages_total`` stays None at submit) and takes the post-OCR
    virtual-page cap path instead. Structure-only assertions, like the
    happy path.
    """
    job_id, _ = submit(
        agent_kv_key, INVOICE_XLSX.read_bytes(), "invoice.xlsx", table_keys("Line items")
    )
    doc = poll(agent_kv_key, job_id)
    assert doc["status"] == "completed", doc
    body = table_result_body(result(agent_kv_key, job_id))
    assert body.get("success") is True, body
    assert isinstance(body["tables"], list), body
    assert "page_count" in body, body


# ---------------------------------------------------------------------------
# 9d. Webhook delivery (operator-gated)
# ---------------------------------------------------------------------------


def test_webhook_delivered_on_completion(
    agent_kv_key: AgentKVAuth, require_llm: None
) -> None:
    """Completion-webhook delivery, end to end: submit with a ``webhook_url``
    pointing at a receiver on the compose host and wait for the POST.

    Operator-gated: the worker's SSRF guards (https + public host, spec
    §6.7) refuse a host-local receiver unless the stack runs with
    ``AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1`` on the ide-callback
    worker (test/dev only), reached via ``host.docker.internal`` (compose
    host-gateway mapping). Skips unless the operator set the same env for
    the test run to declare that setup.
    """
    if os.environ.get("AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        pytest.skip(
            "webhook e2e needs AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1 "
            "on both the ide-callback worker and this test run"
        )

    import http.server
    import threading

    hits: list[dict] = []

    class _Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib API name
            length = int(self.headers.get("Content-Length", "0"))
            hits.append(json.loads(self.rfile.read(length) or b"{}"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):  # keep pytest output pristine
            pass

    server = http.server.HTTPServer(("0.0.0.0", 0), _Receiver)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        job_id, _ = submit(
            agent_kv_key,
            _RENT_ROLL_BYTES,
            "rent_roll.pdf",
            table_keys(),
            webhook_url=f"http://host.docker.internal:{port}/agent-kv-hook",
        )
        doc = poll(agent_kv_key, job_id)
        assert doc["status"] == "completed", doc
        deadline = time.time() + 30
        while time.time() < deadline and not hits:
            time.sleep(0.5)
        assert hits, "no webhook POST arrived within 30s of completion"
        assert hits[0] == {"job_id": job_id, "status": "completed"}, hits
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_concurrency_limit_returns_429(agent_kv_key: AgentKVAuth) -> None:
    """Saturate the org's concurrency limiter; every other submit-based
    scenario in this module runs before this one, and ``tests/groups.yaml``
    pins this whole group ``parallel: false`` -- both for the same reason:

    ``JobCancelView`` marks a job ``CANCELLED`` directly via
    ``AgentKVJob.mark_terminal`` and never touches
    ``AgentKVConcurrencyLimiter`` -- only a job's own *finalize* call
    releases its slot (in a ``finally``, unconditional on whether the
    terminal-state guard actually won -- docs/agent-kv-api.md §11a), and
    that only happens once the executor that picked the job up actually
    runs it to completion/failure and calls back. So immediately after this
    test oversaturates the limiter, the org's concurrency budget stays
    genuinely exhausted for however long those accepted jobs take to
    finalize -- anywhere from seconds to the executor's task time limit.
    Any sibling submit-based test running concurrently with, or soon after,
    this one would risk being 429'd by *this* test's saturation rather than
    by anything it did itself. Running this scenario last (and the group
    serially) removes that risk entirely for this module; the cleanup below
    is a courtesy for whatever runs against this org after it, not a
    correctness requirement for this test itself -- the limiter's own 6h
    slot TTL (``AgentKVConcurrencyLimiter._SLOT_TTL_SECONDS``) is the
    ultimate backstop either way.
    """
    limit = int(os.environ.get("AGENT_KV_CONCURRENT_LIMIT", "5"))
    n = limit + 1

    def _submit(_i: int):
        return _cheap_submit(agent_kv_key)

    accepted_job_ids: list[str] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            responses = list(pool.map(_submit, range(n)))

        statuses = [r.status_code for r in responses]
        assert all(s in (202, 429) for s in statuses), (
            f"unexpected status among {n} concurrent submits "
            f"(only 202/429 are valid outcomes here): {statuses}"
        )
        assert 429 in statuses, (
            f"submitting {n} concurrent jobs against a limit of {limit} "
            f"produced no 429: {statuses}"
        )
        for r in responses:
            if r.status_code == 202:
                accepted_job_ids.append(r.json()["job_id"])
        assert len(accepted_job_ids) <= limit, accepted_job_ids
    finally:
        # Cancelling stops each job's eventual result from ever being
        # readable, but -- per the docstring above -- does NOT itself free
        # its concurrency slot; only that job's own finalize call does.
        for job_id in accepted_job_ids:
            try:
                cancel(agent_kv_key, job_id)
            except Exception:  # noqa: BLE001 - cleanup only, never fail the test on it
                pass

        # Best-effort drain: keep probing with a cheap submission until one
        # is actually accepted again (proof a slot freed up) or the bounded
        # wait runs out. The RESULT is deliberately ignored here -- see the
        # 6h-TTL backstop note in the docstring above; this is a courtesy for
        # whatever runs next, not a correctness requirement for this test.
        _drain_until_slot_free(agent_kv_key)
