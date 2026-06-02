"""Tests for the fairness-key plumbing (PG Queue Phase 5.1).

Today the fairness key is **emitted** by every producer and **read** by
no one. These tests lock in the additive-only invariant so a Phase 8
reader can be added later with confidence that:

1. The shape on the wire is stable (``headers["x-fairness-key"]`` is a
   JSON-safe dict with ``org_id``, ``pipeline_priority``, ``tier``).
2. Omitting fairness on ``dispatch()`` is silent (back-compat for tests
   / system tasks).
3. Every production ``dispatch(...)`` call site DOES pass a fairness
   key (inventory canary).
"""

from __future__ import annotations

import ast
import json
import pathlib
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest
from celery import Celery

from queue_backend import FairnessKey, dispatch
from queue_backend.fairness import (
    DEFAULT_PRIORITY,
    DEFAULT_TIER,
    FAIRNESS_HEADER_NAME,
    MAX_PRIORITY,
    MIN_PRIORITY,
    SYSTEM_TIER,
)

# --- shared scan helpers ---
#
# Pulled out of the audit tests so the tests themselves stay flat
# (cognitive-complexity friendly). Each test then composes these
# generators / predicates without re-walking the directory.

_WORKERS_ROOT = pathlib.Path(__file__).parent.parent
_SKIP_TOP_DIRS = frozenset(
    {"tests", "__pycache__", "htmlcov", ".venv", "queue_backend"}
)


def _iter_production_trees() -> list[tuple[pathlib.Path, ast.AST]]:
    """Yield ``(rel_path, parsed_tree)`` for every production .py file.

    Skips tests/, the seam itself, and anything we can't parse. Pure
    helper — pushing the loop + parse + skip logic here keeps the
    audit tests below SonarCloud's cognitive-complexity threshold.
    """
    out: list[tuple[pathlib.Path, ast.AST]] = []
    for py in _WORKERS_ROOT.rglob("*.py"):
        rel = py.relative_to(_WORKERS_ROOT)
        if rel.parts and rel.parts[0] in _SKIP_TOP_DIRS:
            continue
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:
            continue
        out.append((rel, tree))
    return out


def _aliased_dispatch_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Return ``(lineno, alias)`` for every ``from queue_backend import
    dispatch as <alias>`` in the given tree."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module == "queue_backend"):
            continue
        for alias in node.names:
            if alias.name == "dispatch" and alias.asname not in (None, "dispatch"):
                hits.append((node.lineno, alias.asname))
    return hits


def _dispatch_calls_missing_fairness(tree: ast.AST) -> list[int]:
    """Return linenos of bare ``dispatch(...)`` calls that don't pass
    ``fairness=``.

    Only matches the bare name — method calls like
    ``dispatcher.dispatch(...)`` belong to ExecutionDispatcher
    (executor-side RPC, not a queue boundary) and must not be audited.
    The companion ``_aliased_dispatch_imports`` check forbids alias
    imports so this name-based match has no blind spot.
    """
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (isinstance(callee, ast.Name) and callee.id == "dispatch"):
            continue
        if not any(kw.arg == "fairness" for kw in node.keywords):
            hits.append(node.lineno)
    return hits


# --- FairnessKey value object ---


class TestFairnessKey:
    def test_required_field_is_org_id(self):
        key = FairnessKey(org_id="org-123")
        assert key.org_id == "org-123"
        assert key.pipeline_priority == DEFAULT_PRIORITY
        assert key.tier == DEFAULT_TIER

    def test_org_id_can_be_none_for_system_tasks(self):
        key = FairnessKey.system()
        assert key.org_id is None

    def test_for_org_convenience_constructor(self):
        key = FairnessKey.for_org("org-1")
        assert key.org_id == "org-1"
        assert key.pipeline_priority == DEFAULT_PRIORITY
        assert key.tier == DEFAULT_TIER

    def test_for_org_accepts_overrides(self):
        key = FairnessKey.for_org("org-1", pipeline_priority=80, tier="enterprise")
        assert key.pipeline_priority == 80
        assert key.tier == "enterprise"

    def test_is_frozen(self):
        key = FairnessKey(org_id="x")
        with pytest.raises(FrozenInstanceError):
            key.org_id = "y"  # type: ignore[misc]

    def test_priority_below_range_rejected(self):
        with pytest.raises(ValueError, match="pipeline_priority out of range"):
            FairnessKey(org_id="x", pipeline_priority=MIN_PRIORITY - 1)

    def test_priority_above_range_rejected(self):
        with pytest.raises(ValueError, match="pipeline_priority out of range"):
            FairnessKey(org_id="x", pipeline_priority=MAX_PRIORITY + 1)

    def test_priority_boundaries_accepted(self):
        FairnessKey(org_id="x", pipeline_priority=MIN_PRIORITY)
        FairnessKey(org_id="x", pipeline_priority=MAX_PRIORITY)

    def test_for_org_rejects_misspelled_kwargs(self):
        """``priority=`` (instead of ``pipeline_priority=``) and other
        typos must fail loudly, not silently fall back to defaults."""
        with pytest.raises(TypeError, match="priority"):
            FairnessKey.for_org("org-1", priority=80)  # type: ignore[call-arg]
        with pytest.raises(TypeError, match="tiers"):
            FairnessKey.for_org("org-1", tiers="enterprise")  # type: ignore[call-arg]

    def test_for_org_rejects_none_org_id(self):
        """``for_org(None)`` would produce an inconsistent key
        (``tier="standard"`` with no org). Callers must use
        :meth:`FairnessKey.system` for tasks without tenant context.
        """
        with pytest.raises(ValueError, match="use FairnessKey.system"):
            FairnessKey.for_org(None)  # type: ignore[arg-type]

    def test_to_dict_shape(self):
        key = FairnessKey(org_id="org-1", pipeline_priority=80, tier="enterprise")
        assert key.to_dict() == {
            "org_id": "org-1",
            "pipeline_priority": 80,
            "tier": "enterprise",
        }

    def test_to_dict_is_json_safe(self):
        """The dict must round-trip through ``json.dumps`` — Celery's
        default serializer is JSON."""
        key = FairnessKey.for_org("org-1", pipeline_priority=80, tier="enterprise")
        round_tripped = json.loads(json.dumps(key.to_dict()))
        assert round_tripped == key.to_dict()

    def test_system_key_encodes_partition_in_tier(self):
        """``FairnessKey.system()`` must put the partition in ``tier``
        (not implicit via ``org_id is None``) so the Phase 8 scheduler
        can match on a single closed-set field."""
        key = FairnessKey.system()
        assert key.org_id is None
        assert key.tier == SYSTEM_TIER

    def test_system_key_round_trips(self):
        """``org_id=None`` is JSON-safe (becomes JSON null) and the
        tier is preserved through serialisation."""
        key = FairnessKey.system()
        round_tripped = json.loads(json.dumps(key.to_dict()))
        assert round_tripped == {
            "org_id": None,
            "pipeline_priority": DEFAULT_PRIORITY,
            "tier": SYSTEM_TIER,
        }


# --- dispatch() integration ---


class TestDispatchAttachesFairness:
    def test_omitted_fairness_no_header_sent(self):
        """Back-compat: ``dispatch(...)`` without ``fairness=`` does not
        attach a headers dict — Celery sees the same args/kwargs/queue
        call shape as before Phase 5.1."""
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", kwargs={"foo": "bar"})

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["headers"] is None
        # Business kwargs untouched.
        assert call_kwargs["kwargs"] == {"foo": "bar"}

    def test_provided_fairness_attached_as_message_header(self):
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                "any_task",
                kwargs={"foo": "bar"},
                fairness=FairnessKey.for_org("org-1", pipeline_priority=80),
            )

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["headers"] == {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "pipeline_priority": 80,
                "tier": DEFAULT_TIER,
            }
        }
        # Critically: the business kwargs must NOT contain the fairness
        # slot — otherwise tasks without ``**kwargs`` blow up on the
        # extra keyword argument.
        sent_kwargs = call_kwargs["kwargs"]
        assert sent_kwargs == {"foo": "bar"}
        assert FAIRNESS_HEADER_NAME not in sent_kwargs

    def test_fairness_with_no_business_kwargs(self):
        """``dispatch`` accepts fairness even when caller passes no kwargs.
        Business kwargs stay None — header carries the routing data."""
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", fairness=FairnessKey.system())

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["kwargs"] is None
        assert call_kwargs["headers"] == {
            FAIRNESS_HEADER_NAME: {
                "org_id": None,
                "pipeline_priority": DEFAULT_PRIORITY,
                "tier": SYSTEM_TIER,
            }
        }

    def test_caller_kwargs_not_mutated_in_place(self):
        """``dispatch`` must not mutate the caller's kwargs dict —
        guards against compounding state across calls if implementation
        ever drifts back to a kwargs-merge strategy."""
        caller_kwargs = {"foo": "bar"}
        with patch("queue_backend.dispatch.current_app"):
            dispatch(
                "any_task",
                kwargs=caller_kwargs,
                fairness=FairnessKey.for_org("org-1"),
            )

        assert caller_kwargs == {"foo": "bar"}
        assert FAIRNESS_HEADER_NAME not in caller_kwargs


# --- Inventory canary: every production dispatch() must pass fairness ---


class TestDispatchCallSitesPassFairness:
    """AST-based audit: every ``dispatch(...)`` call in production code
    paths must include a ``fairness=`` keyword. Tests and the seam
    module itself are exempt (they exercise/define the mechanism)."""

    def test_dispatch_must_be_imported_unaliased(self):
        """The fairness canary below only matches the bare name
        ``dispatch``. If a producer imports it as ``from queue_backend
        import dispatch as foo``, the canary would silently miss any
        ``foo(...)`` call. Forbid the alias form so the canary stays
        complete.
        """
        aliased = [
            f"{rel}:{lineno} (as {alias})"
            for rel, tree in _iter_production_trees()
            for lineno, alias in _aliased_dispatch_imports(tree)
        ]
        assert aliased == [], (
            "``queue_backend.dispatch`` must be imported under its real "
            "name — alias imports defeat the fairness inventory canary. "
            "Found:\n  " + "\n  ".join(aliased)
        )

    def test_every_production_dispatch_passes_fairness(self):
        offenders = [
            f"{rel}:{lineno}"
            for rel, tree in _iter_production_trees()
            for lineno in _dispatch_calls_missing_fairness(tree)
        ]
        assert offenders == [], (
            "Production dispatch(...) call site(s) missing fairness=. "
            "Every production dispatch must declare its fairness key — "
            "pass ``fairness=FairnessKey.system()`` for system / "
            "cross-org tasks if there's no tenant context. Found:\n  "
            + "\n  ".join(offenders)
        )


# --- No worker reads the fairness slot yet (additive-only invariant) ---


class TestNoConsumerYet:
    """Phase 5.1 is *additive only* — Phase 8 will introduce the reader.

    Until then, no code path in ``workers/`` should reference
    ``x-fairness-key`` or ``FAIRNESS_HEADER_NAME`` outside the seam +
    these tests. If a consumer slips in earlier, this canary fails and
    we can re-evaluate the rollout order.
    """

    def test_no_consumer_reads_fairness_header(self):
        forbidden_tokens = ("x-fairness-key", "FAIRNESS_HEADER_NAME")

        readers: list[str] = []
        for py in _WORKERS_ROOT.rglob("*.py"):
            rel = py.relative_to(_WORKERS_ROOT)
            if rel.parts and rel.parts[0] in _SKIP_TOP_DIRS:
                continue
            for line_no, line in enumerate(py.read_text().splitlines(), start=1):
                if any(token in line for token in forbidden_tokens):
                    readers.append(f"{rel}:{line_no}")

        assert readers == [], (
            "Found reader(s) of the fairness slot before Phase 8. "
            "Phase 5.1 is additive-only — no consumer should exist yet. "
            "Found:\n  " + "\n  ".join(readers)
        )


# --- End-to-end: header survives Celery's signature pipeline ---


class TestHeaderSurvivesCeleryPipeline:
    """Belt-and-braces over the mock-based tests above.

    Real Celery in eager mode with a memory broker: enqueue a task via
    ``dispatch(...)``, capture the message ``Celery`` would put on the
    wire, and assert the fairness header is present in the right shape.
    Catches the (rare but expensive) case where a future Celery or
    kombu serializer upgrade silently drops unknown headers.
    """

    def test_header_present_on_outbound_message(self):
        # Self-contained Celery app on a memory broker — exercises the
        # real ``send_task`` codepath without needing RabbitMQ. We don't
        # need eager execution; the assertion is on the message Celery
        # would put on the wire, captured via a wraps= patch.
        app = Celery("test_fairness_e2e", broker="memory://", backend="cache+memory://")

        with patch("queue_backend.dispatch.current_app", app), patch.object(
            app, "send_task", wraps=app.send_task
        ) as wrapped_send:
            dispatch(
                "qb.e2e.echo",
                fairness=FairnessKey.for_org(
                    "org-1", pipeline_priority=80, tier="enterprise"
                ),
            )

        # ``send_task`` is invoked with the headers dict carrying the
        # fairness payload in the documented shape.
        call_headers = wrapped_send.call_args.kwargs["headers"]
        assert call_headers == {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "pipeline_priority": 80,
                "tier": "enterprise",
            }
        }
