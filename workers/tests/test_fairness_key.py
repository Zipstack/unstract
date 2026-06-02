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
from unittest.mock import patch

from queue_backend import FairnessKey, dispatch
from queue_backend.fairness import (
    DEFAULT_PRIORITY,
    DEFAULT_TIER,
    FAIRNESS_HEADER_NAME,
)


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
        try:
            key.org_id = "y"  # type: ignore[misc]
        except Exception as exc:
            assert "frozen" in str(exc).lower() or isinstance(exc, AttributeError)
        else:
            raise AssertionError("FairnessKey should be frozen / immutable")

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

    def test_system_key_round_trips(self):
        """``org_id=None`` is JSON-safe (becomes JSON null)."""
        key = FairnessKey.system()
        round_tripped = json.loads(json.dumps(key.to_dict()))
        assert round_tripped == {
            "org_id": None,
            "pipeline_priority": DEFAULT_PRIORITY,
            "tier": DEFAULT_TIER,
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
                "tier": DEFAULT_TIER,
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

    def test_every_production_dispatch_passes_fairness(self):
        workers_root = pathlib.Path(__file__).parent.parent
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv", "queue_backend"}

        class FairnessAuditor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.violations: list[int] = []

            def visit_Call(self, node: ast.Call) -> None:
                # Only match bare ``dispatch(...)`` — i.e. the function
                # imported as ``from queue_backend import dispatch``.
                # Method calls like ``dispatcher.dispatch(...)`` belong
                # to ExecutionDispatcher (executor-side RPC) and aren't
                # queue boundaries — different concept, must not be
                # audited here.
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id == "dispatch":
                    has_fairness = any(
                        kw.arg == "fairness" for kw in node.keywords
                    )
                    if not has_fairness:
                        self.violations.append(node.lineno)
                self.generic_visit(node)

        offenders: list[str] = []
        for py in workers_root.rglob("*.py"):
            rel = py.relative_to(workers_root)
            if rel.parts and rel.parts[0] in skip_top_dirs:
                continue
            try:
                tree = ast.parse(py.read_text(), filename=str(py))
            except SyntaxError:
                continue
            auditor = FairnessAuditor()
            auditor.visit(tree)
            for line_no in auditor.violations:
                offenders.append(f"{rel}:{line_no}")

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
        workers_root = pathlib.Path(__file__).parent.parent
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv", "queue_backend"}
        forbidden_tokens = ("x-fairness-key", "FAIRNESS_HEADER_NAME")

        readers: list[str] = []
        for py in workers_root.rglob("*.py"):
            rel = py.relative_to(workers_root)
            if rel.parts and rel.parts[0] in skip_top_dirs:
                continue
            for line_no, line in enumerate(py.read_text().splitlines(), start=1):
                if any(token in line for token in forbidden_tokens):
                    readers.append(f"{rel}:{line_no}")

        assert readers == [], (
            "Found reader(s) of the fairness slot before Phase 8. "
            "Phase 5.1 is additive-only — no consumer should exist yet. "
            "Found:\n  " + "\n  ".join(readers)
        )
