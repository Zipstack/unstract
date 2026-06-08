"""Tests for the fairness-key plumbing (PG Queue Phase 5.1)."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest
from celery import Celery

from queue_backend import FairnessKey, dispatch
from queue_backend.fairness import (
    DEFAULT_PRIORITY,
    FAIRNESS_HEADER_NAME,
    MAX_PRIORITY,
    MIN_PRIORITY,
    WorkloadType,
)
from .canary_helpers import (
    DEFAULT_SKIP_TOP_DIRS,
    WORKERS_ROOT,
    iter_production_trees,
)

# Fairness-canary helpers also skip the seam module itself (it
# legitimately defines and exports the fairness constants).
_SKIP_TOP_DIRS = DEFAULT_SKIP_TOP_DIRS | frozenset({"queue_backend"})


def _trees():
    return iter_production_trees(skip_top_dirs=_SKIP_TOP_DIRS)


def _aliased_dispatch_imports(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ImportFrom) and node.module == "queue_backend"):
            continue
        for alias in node.names:
            if alias.name == "dispatch" and alias.asname not in (None, "dispatch"):
                hits.append((node.lineno, alias.asname))
    return hits


def _dispatch_calls_missing_fairness(tree: ast.AST) -> list[int]:
    # Only matches the bare name ``dispatch`` — ``dispatcher.dispatch(...)``
    # is ExecutionDispatcher (executor RPC), a different concept.
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


class TestFairnessKey:
    def test_minimal_construction(self):
        key = FairnessKey(org_id="org-123", workload_type=WorkloadType.API)
        assert key.org_id == "org-123"
        assert key.workload_type == "api"
        assert key.pipeline_priority == DEFAULT_PRIORITY  # default 5

    def test_org_id_can_be_none(self):
        key = FairnessKey(org_id=None, workload_type=WorkloadType.API)
        assert key.org_id is None

    def test_workload_type_non_api(self):
        key = FairnessKey(org_id="x", workload_type=WorkloadType.NON_API)
        assert key.workload_type == "non_api"
        assert key.workload_type == WorkloadType.NON_API

    def test_pipeline_priority_override(self):
        key = FairnessKey(org_id="x", workload_type=WorkloadType.API, pipeline_priority=9)
        assert key.pipeline_priority == 9

    def test_is_frozen(self):
        key = FairnessKey(org_id="x", workload_type=WorkloadType.API)
        with pytest.raises(FrozenInstanceError):
            key.org_id = "y"  # type: ignore[misc]

    def test_priority_below_range_rejected(self):
        with pytest.raises(ValueError, match="pipeline_priority out of range"):
            FairnessKey(
                org_id="x", workload_type=WorkloadType.API, pipeline_priority=MIN_PRIORITY - 1
            )

    def test_priority_above_range_rejected(self):
        with pytest.raises(ValueError, match="pipeline_priority out of range"):
            FairnessKey(
                org_id="x", workload_type=WorkloadType.API, pipeline_priority=MAX_PRIORITY + 1
            )

    def test_priority_boundaries_accepted(self):
        FairnessKey(org_id="x", workload_type=WorkloadType.API, pipeline_priority=MIN_PRIORITY)
        FairnessKey(org_id="x", workload_type=WorkloadType.API, pipeline_priority=MAX_PRIORITY)

    def test_typo_in_field_name_raises(self):
        with pytest.raises(TypeError, match="pipeline_prio"):
            FairnessKey(
                org_id="x",
                workload_type=WorkloadType.API,
                pipeline_prio=9,  # type: ignore[call-arg]
            )

    def test_to_dict_shape(self):
        key = FairnessKey(
            org_id="org-1", workload_type=WorkloadType.NON_API, pipeline_priority=9
        )
        assert key.to_dict() == {
            "org_id": "org-1",
            "workload_type": "non_api",
            "pipeline_priority": 9,
        }

    def test_to_dict_uses_plain_string_not_enum_member(self):
        # Downstream consumers shouldn't need to import WorkloadType.
        key = FairnessKey(org_id="x", workload_type=WorkloadType.API)
        wt = key.to_dict()["workload_type"]
        assert type(wt) is str
        assert wt == "api"

    def test_to_dict_is_json_safe(self):
        key = FairnessKey(
            org_id="org-1", workload_type=WorkloadType.API, pipeline_priority=7
        )
        round_tripped = json.loads(json.dumps(key.to_dict()))
        assert round_tripped == key.to_dict()

    def test_orgless_key_round_trips(self):
        key = FairnessKey(org_id=None, workload_type=WorkloadType.API)
        round_tripped = json.loads(json.dumps(key.to_dict()))
        assert round_tripped == {
            "org_id": None,
            "workload_type": "api",
            "pipeline_priority": DEFAULT_PRIORITY,
        }


# --- dispatch() integration ---


class TestDispatchAttachesFairness:
    def test_omitted_fairness_no_header_sent(self):
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("any_task", kwargs={"foo": "bar"})

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["headers"] is None
        assert call_kwargs["kwargs"] == {"foo": "bar"}

    def test_explicit_fairness_none_no_header_sent(self):
        # Documented opt-out for non-workflow dispatches.
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("send_webhook_notification", kwargs={"x": 1}, fairness=None)

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["headers"] is None
        assert call_kwargs["kwargs"] == {"x": 1}

    def test_provided_fairness_attached_as_message_header(self):
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                "any_task",
                kwargs={"foo": "bar"},
                fairness=FairnessKey(
                    org_id="org-1", workload_type=WorkloadType.API, pipeline_priority=9
                ),
            )

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["headers"] == {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "workload_type": "api",
                "pipeline_priority": 9,
            }
        }
        # Business kwargs must NOT contain the fairness slot — tasks
        # without **kwargs would break.
        sent_kwargs = call_kwargs["kwargs"]
        assert sent_kwargs == {"foo": "bar"}
        assert FAIRNESS_HEADER_NAME not in sent_kwargs

    def test_fairness_with_no_business_kwargs(self):
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                "any_task",
                fairness=FairnessKey(org_id=None, workload_type=WorkloadType.NON_API),
            )

        call_kwargs = mock_app.send_task.call_args.kwargs
        assert call_kwargs["kwargs"] is None
        assert call_kwargs["headers"] == {
            FAIRNESS_HEADER_NAME: {
                "org_id": None,
                "workload_type": "non_api",
                "pipeline_priority": DEFAULT_PRIORITY,
            }
        }

    def test_caller_kwargs_not_mutated_in_place(self):
        caller_kwargs = {"foo": "bar"}
        with patch("queue_backend.dispatch.current_app"):
            dispatch(
                "any_task",
                kwargs=caller_kwargs,
                fairness=FairnessKey(org_id="org-1", workload_type=WorkloadType.API),
            )

        assert caller_kwargs == {"foo": "bar"}
        assert FAIRNESS_HEADER_NAME not in caller_kwargs


class TestDispatchCallSitesPassFairness:
    """AST audit: every production ``dispatch(...)`` declares fairness."""

    def test_dispatch_must_be_imported_unaliased(self):
        # Alias imports would defeat the bare-name canary below.
        aliased = [
            f"{rel}:{lineno} (as {alias})"
            for rel, tree in _trees()
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
            for rel, tree in _trees()
            for lineno in _dispatch_calls_missing_fairness(tree)
        ]
        assert offenders == [], (
            "Production dispatch(...) call site(s) missing fairness=. "
            "Every production dispatch must declare its fairness — pass "
            "``fairness=FairnessKey(org_id=..., workload_type=WorkloadType...)`` "
            "for a workflow-execution dispatch, or ``fairness=None`` "
            "for a worker-internal task that doesn't start a workflow "
            "execution. Found:\n  " + "\n  ".join(offenders)
        )


class TestNoConsumerYet:
    """Additive-only invariant — no production code reads the slot yet."""

    def test_no_consumer_reads_fairness_header(self):
        forbidden_tokens = ("x-fairness-key", "FAIRNESS_HEADER_NAME")

        readers: list[str] = []
        for py in WORKERS_ROOT.rglob("*.py"):
            rel = py.relative_to(WORKERS_ROOT)
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


class TestHeaderSurvivesCeleryPipeline:
    """End-to-end: header survives Celery's real send_task code path."""

    def test_header_present_on_outbound_message(self):
        app = Celery(
            "test_fairness_e2e", broker="memory://", backend="cache+memory://"
        )

        with patch("queue_backend.dispatch.current_app", app), patch.object(
            app, "send_task", wraps=app.send_task
        ) as wrapped_send:
            dispatch(
                "qb.e2e.echo",
                fairness=FairnessKey(
                    org_id="org-1",
                    workload_type=WorkloadType.NON_API,
                    pipeline_priority=9,
                ),
            )

        call_headers = wrapped_send.call_args.kwargs["headers"]
        assert call_headers == {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "workload_type": "non_api",
                "pipeline_priority": 9,
            }
        }
