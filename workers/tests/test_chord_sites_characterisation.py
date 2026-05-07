"""Characterisation tests for the two ``celery.chord`` call sites.

These are the two places in ``workers/`` source that invoke ``chord(...)``
directly. PR #13 will replace both with a transport-agnostic ``Barrier``
abstraction matching the labs target architecture's ``DECR remaining:{exec_id}``
pattern.

This test suite locks down the **current** chord invocation contract so the
migration can be proved equivalent. Chord is the highest-risk Celery construct
called out in the PG Queue decision doc (silent task drops at ~130K-task scale)
— characterising it before refactor is critical.

Sites:
1. ``shared/workflow/execution/orchestration_utils.py`` — ``WorkflowOrchestrationUtils.create_chord_execution`` (the centralised helper).
2. ``api-deployment/tasks.py`` — inline chord inside ``_run_workflow_api``.
   Site 2 is exercised only via the inventory test (full characterisation
   requires heavy mocking of the enclosing 273-line function — out of scope
   for a smoke/characterisation pass).
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

        with patch(
            "shared.workflow.execution.orchestration_utils.chord"
        ) as mock_chord:
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

        with patch(
            "shared.workflow.execution.orchestration_utils.chord"
        ) as mock_chord:
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

        with patch(
            "shared.workflow.execution.orchestration_utils.chord"
        ) as mock_chord:
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

        with patch(
            "shared.workflow.execution.orchestration_utils.chord"
        ) as mock_chord:
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

        with patch(
            "shared.workflow.execution.orchestration_utils.chord"
        ) as mock_chord:
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

        mock_static.assert_called_once_with(
            batch,
            "process_batch_callback",
            kwargs,
            "file_processing_callback",
            task.app,
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
    """Exactly two chord call sites must exist in workers/ source.

    If a third appears, this test fails so PR #13's migration can't silently
    miss it.
    """

    def test_only_two_known_chord_call_sites_in_workers(self):
        """Count chord(...) invocations (not imports) in workers/ source."""
        import pathlib
        import re

        workers_root = pathlib.Path(__file__).parent.parent
        # Anchor to the top-level directory relative to workers_root so we
        # don't accidentally exclude legitimately-named subdirectories like
        # `workers/shared/tests_helpers/`.
        skip_top_dirs = {"tests", "__pycache__", "htmlcov", ".venv"}

        # Match `chord(` as a function call — excludes the bare import line
        # `from celery import chord` and helper method names like `create_chord`.
        # The regex requires `chord` to be preceded by start-of-line / whitespace
        # / `=` / `(` (i.e., a true call expression), not as part of a longer
        # identifier such as `create_chord`.
        pattern = re.compile(r"(?:^|[\s=(])chord\(")

        hits = []
        for py in workers_root.rglob("*.py"):
            rel_parts = py.relative_to(workers_root).parts
            if rel_parts and rel_parts[0] in skip_top_dirs:
                continue
            text = py.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(f"{py.relative_to(workers_root)}:{line_no}")

        # Expected exactly two — in orchestration_utils.py and api-deployment/tasks.py.
        assert len(hits) == 2, (
            f"Expected exactly 2 chord(...) call sites in workers/, found "
            f"{len(hits)}:\n  " + "\n  ".join(hits)
        )
        joined = " ".join(hits)
        assert "shared/workflow/execution/orchestration_utils.py" in joined
        assert "api-deployment/tasks.py" in joined

    def test_chord_import_only_in_two_files(self):
        """`from celery import chord` should appear in exactly the two files
        that actually invoke chord — no other imports lurking."""
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

        assert len(hits) == 2, (
            f"Expected `from celery import chord` in exactly 2 files, found "
            f"{len(hits)}:\n  " + "\n  ".join(hits)
        )
        # Sanity: same files as the call-site canary above.  If the imports
        # ever migrate to different files while count stays at 2, this catches
        # it — preventing a silent miss during the Barrier migration.
        joined = " ".join(hits)
        assert "shared/workflow/execution/orchestration_utils.py" in joined
        assert "api-deployment/tasks.py" in joined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
