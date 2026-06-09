"""Characterisation tests for the chord-callback boundary, now lifted
behind the ``Barrier`` abstraction (PG Queue Phase 6a).

Originally written to lock down the inline ``celery.chord(...)`` calls
at two call sites before they were lifted. Post-uplift the inline
calls are gone — both call sites delegate to
``WorkflowOrchestrationUtils.create_chord_execution`` which in turn
delegates to ``CeleryChordBarrier.enqueue(...)``. The single remaining
``chord(...)`` call lives inside ``workers/queue_backend/barrier.py``.

Sites covered (assertions unchanged from the original pre-uplift
suite — they characterise the **same** ``chord(header)(body)``
contract, now reached one indirection later):
1. ``shared/workflow/execution/orchestration_utils.py`` —
   ``WorkflowOrchestrationUtils.create_chord_execution`` (centralised helper).
2. ``api-deployment/tasks.py`` — same helper, called inline inside
   ``_run_workflow_api`` (post-uplift it no longer calls ``chord(...)``
   directly; covered by the inventory test below).

Chord is the highest-risk Celery construct called out in the PG Queue
decision doc (silent task drops at ~130K-task scale). A future
Phase 6b will introduce ``RedisDecrBarrier`` as a second implementation
behind a flag; these tests stay green through that transition because
they characterise the **Celery chord** code path specifically.
"""

from unittest.mock import MagicMock, patch

import pytest


# --- Site 1: WorkflowOrchestrationUtils.create_chord_execution ---


class TestCreateChordExecution:
    """Characterise the centralised chord helper.

    This is the easily-testable site. PR #13 should route both this helper
    AND the inline call (Site 2) through the new Barrier abstraction.
    """

    def _make_app_instance(self):
        """Build a Celery app-shaped mock with a working ``.signature(...)``."""
        app = MagicMock()
        # signature() returns an opaque "signature" object — represent it as a
        # MagicMock that we can assert on by identity later.
        app.signature.return_value = MagicMock(name="callback_signature")
        return app

    def test_empty_batch_tasks_returns_none_and_skips_chord(self):
        """Zero files: helper short-circuits with None and never calls chord()."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app = self._make_app_instance()

        with patch("queue_backend.barrier.chord") as mock_chord:
            result = WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=[],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1", "pipeline_id": "pipe-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        assert result is None
        mock_chord.assert_not_called()

    def test_non_empty_batch_tasks_invokes_chord(self):
        """Non-empty batch: chord(batch_tasks)(callback_signature) is called."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app = self._make_app_instance()
        batch_tasks = [MagicMock(name="batch_task_1"), MagicMock(name="batch_task_2")]

        with patch("queue_backend.barrier.chord") as mock_chord:
            # chord(batch_tasks) returns a chord object; calling it with the
            # callback signature returns the chord result.  Both calls must
            # happen for this characterisation.
            chord_obj = MagicMock(name="chord_object")
            mock_chord.return_value = chord_obj

            WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=batch_tasks,
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        # First call: chord(batch_tasks)
        mock_chord.assert_called_once_with(batch_tasks)
        # Second call: chord_obj(callback_signature) — applies the chord
        chord_obj.assert_called_once_with(app.signature.return_value)

    def test_callback_signature_is_built_with_correct_kwargs(self):
        """The callback signature must be created with the exact task name,
        kwargs, and queue passed in.  PR #13 must preserve these."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app = self._make_app_instance()
        batch_tasks = [MagicMock(name="batch")]
        callback_kwargs = {
            "execution_id": "exec-42",
            "pipeline_id": "pipe-7",
            "organization_id": "org-x",
        }

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.return_value = MagicMock()
            WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=batch_tasks,
                callback_task_name="process_batch_callback_api",
                callback_kwargs=callback_kwargs,
                callback_queue="api_file_processing_callback",
                app_instance=app,
            )

        app.signature.assert_called_once_with(
            "process_batch_callback_api",
            kwargs=callback_kwargs,
            queue="api_file_processing_callback",
        )

    def test_returns_chord_result_object(self):
        """The helper must return whatever ``chord(...)(...)`` returns —
        callers depend on this return value to track the chord."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app = self._make_app_instance()

        with patch("queue_backend.barrier.chord") as mock_chord:
            chord_obj = MagicMock()
            chord_result = MagicMock(name="chord_result_object")
            chord_obj.return_value = chord_result
            mock_chord.return_value = chord_obj

            result = WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=[MagicMock()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        assert result is chord_result

    def test_chord_failure_is_re_raised_after_logging(self):
        """If chord() raises, the helper logs and re-raises (not swallowed)."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app = self._make_app_instance()

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.side_effect = RuntimeError("broker exploded")

            with pytest.raises(RuntimeError, match="broker exploded"):
                WorkflowOrchestrationUtils.create_chord_execution(
                    batch_tasks=[MagicMock()],
                    callback_task_name="process_batch_callback",
                    callback_kwargs={"execution_id": "exec-1"},
                    callback_queue="file_processing_callback",
                    app_instance=app,
                )


# --- Site 1 (mixin wrapper): WorkflowOrchestrationMixin.create_chord ---


class TestWorkflowOrchestrationMixinCreateChord:
    """Characterise the mixin wrapper around ``create_chord_execution``.

    The mixin adds two unique behaviours over the static helper:
    1. Extracts ``self.app`` from the task context.
    2. Raises ``RuntimeError`` when no app is bound to the task.

    Both must be preserved by PR #13 when it lifts the mixin to use Barrier.
    """

    def test_create_chord_extracts_app_from_self_and_delegates(self):
        """The mixin must read ``self.app`` and forward it to the static helper."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationMixin,
            WorkflowOrchestrationUtils,
        )

        # Build a synthetic task-like object carrying an `app` attribute.
        task = type("FakeTask", (WorkflowOrchestrationMixin,), {})()
        task.app = MagicMock(name="celery_app")
        task.app.signature.return_value = MagicMock(name="callback_signature")

        with patch.object(
            WorkflowOrchestrationUtils, "create_chord_execution"
        ) as mock_static:
            mock_static.return_value = MagicMock(name="chord_result")
            batch = [MagicMock()]
            kwargs = {"execution_id": "exec-mixin"}
            task.create_chord(
                batch_tasks=batch,
                callback_task_name="process_batch_callback",
                callback_kwargs=kwargs,
                callback_queue="file_processing_callback",
            )

        # Mixin now forwards ``fairness=`` (None when caller omits it)
        # to ``create_chord_execution``. The positional args stay the
        # same.
        mock_static.assert_called_once_with(
            batch,
            "process_batch_callback",
            kwargs,
            "file_processing_callback",
            task.app,
            fairness=None,
        )

    def test_create_chord_raises_when_no_app_bound(self):
        """No ``self.app`` (e.g., called outside a Celery task context):
        the mixin must raise ``RuntimeError`` rather than silently failing
        or passing ``None`` downstream to chord()."""
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationMixin,
        )

        task = type("FakeTask", (WorkflowOrchestrationMixin,), {})()
        # Deliberately do NOT set task.app — leave it absent.

        with pytest.raises(RuntimeError, match="Celery app instance not available"):
            task.create_chord(
                batch_tasks=[MagicMock()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
            )


# --- Cross-site invariant: chord call-site inventory ---


class TestChordSiteInventory:
    """Post-Barrier-uplift invariant: exactly ONE ``chord(...)`` call
    site, inside ``queue_backend/barrier.py``.

    Before the uplift there were two inline ``chord(...)`` calls (in
    ``orchestration_utils.py`` and ``api-deployment/tasks.py``). The
    refactor lifted both behind ``CeleryChordBarrier`` so the chord
    primitive has a single home — a future ``RedisDecrBarrier`` swap
    can target one location instead of chasing call sites.

    If a third ``chord(...)`` call appears anywhere outside
    ``barrier.py``, this test fails — preventing a silent regression
    where a future PR bypasses the abstraction.
    """

    _CHORD_HOST = "queue_backend/barrier.py"

    def test_chord_invocation_lives_only_in_barrier(self):
        """Count chord(...) invocations (not imports) in workers/ source.

        Tightened regex (after the original ``(?:^|[\\s=(])chord\\(``
        could match docstring prose mentioning ``chord(...)`` after
        whitespace): now requires assignment form ``= chord(`` (with
        optional whitespace), which matches the production call at
        ``barrier.py``'s ``result = chord(header_tasks)(callback_signature)``
        but rejects docstring / comment mentions like ``the chord(...)
        primitive``.

        Comment / docstring lines are also explicitly skipped as
        belt-and-suspenders against a future call site that lacks the
        ``=`` prefix (e.g. a return-value-discarded ``chord(...)``).
        """
        import pathlib
        import re

        workers_root = pathlib.Path(__file__).parent.parent
        # Anchor to the top-level directory relative to workers_root so we
        # don't accidentally exclude legitimately-named subdirectories like
        # `workers/shared/tests_helpers/`.
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv"}

        # Assignment-form ``= chord(`` — production call sites all
        # capture the AsyncResult into a variable. Docstring prose
        # never uses this form.
        pattern = re.compile(r"=\s*chord\(")

        hits = []
        for py in workers_root.rglob("*.py"):
            rel_parts = py.relative_to(workers_root).parts
            if rel_parts and rel_parts[0] in skip_top_dirs:
                continue
            text = py.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                # Skip pure comment lines (belt-and-suspenders — the
                # regex already rejects most of these via the ``=``
                # prefix requirement, but a comment like ``# x = chord(...)``
                # would otherwise sneak through).
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        assert len(hits) == 1, (
            "Expected exactly 1 chord(...) call site in workers/ (inside "
            f"{self._CHORD_HOST}), found {len(hits)}:\n  "
            + "\n  ".join(hits)
            + "\nPhase 6a lifted both call sites behind CeleryChordBarrier — "
            "a new direct chord(...) call bypasses the Barrier abstraction "
            "and breaks the future Phase 6b RedisDecrBarrier swap point."
        )
        assert self._CHORD_HOST in hits[0], (
            f"chord(...) call must live in {self._CHORD_HOST}, found at {hits[0]}"
        )

    def test_chord_import_only_in_barrier(self):
        """`from celery import chord` should appear in exactly one file —
        ``queue_backend/barrier.py`` — post-Barrier uplift."""
        import pathlib
        import re

        workers_root = pathlib.Path(__file__).parent.parent
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv"}

        pattern = re.compile(r"^\s*from\s+celery\s+import\s+chord\b")

        hits = []
        for py in workers_root.rglob("*.py"):
            rel_parts = py.relative_to(workers_root).parts
            if rel_parts and rel_parts[0] in skip_top_dirs:
                continue
            text = py.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        assert len(hits) == 1, (
            f"Expected `from celery import chord` in exactly 1 file, found "
            f"{len(hits)}:\n  " + "\n  ".join(hits)
        )
        assert self._CHORD_HOST in hits[0], (
            f"chord import must live in {self._CHORD_HOST}, found at {hits[0]}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
