"""Wire-shape characterisation for the chord-callback boundary.

Locks the on-wire contract for the producer paths that feed
``process_batch_callback`` (general path) and ``process_batch_callback_api``
(API path). Producers build typed dataclasses and serialise via
``.to_dict()``.

Three layers of test:

1. **Dataclass wire shape** — ``to_dict`` / ``from_dict`` round-trip
   preserves every consumer-read field; JSON-safe.
2. **Producer binding** — drives the real producer functions
   (``_compile_batch_result``, ``_process_single_file_api``). Catches
   reverts at the producer site that a dataclass-only test would miss.
3. **Real-consumer tolerance** — drives the real
   ``aggregate_file_batch_results`` consumer against the typed wire
   shape. Catches mismatches the producer-only test would miss.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from shared.processing.files.time_utils import aggregate_file_batch_results
from unstract.core.worker_models import (
    ApiDeploymentResultStatus,
    BatchExecutionResult,
    FileExecutionResult,
    SkipReason,
)


class TestBatchExecutionResultWireShape:
    """General path (``process_file_batch`` returns this shape)."""

    def _make(self) -> BatchExecutionResult:
        return BatchExecutionResult(
            total_files=10,
            successful_files=7,
            failed_files=2,
            execution_time=12.5,
            skipped_already_completed=1,
            skipped_active_duplicate=0,
            organization_id="org-test",
        )

    def test_wire_contains_consumer_read_fields(self):
        wire = self._make().to_dict()
        for key in (
            "total_files",
            "successful_files",
            "failed_files",
            "execution_time",
            "file_results",
        ):
            assert key in wire, f"consumer-read field missing: {key}"

    def test_wire_carries_extended_optional_fields(self):
        wire = self._make().to_dict()
        assert wire["skipped_already_completed"] == 1
        assert wire["skipped_active_duplicate"] == 0
        assert wire["organization_id"] == "org-test"

    def test_round_trip_preserves_all_fields(self):
        original = self._make()
        round_tripped = BatchExecutionResult.from_dict(original.to_dict())
        assert round_tripped.total_files == original.total_files
        assert round_tripped.successful_files == original.successful_files
        assert round_tripped.failed_files == original.failed_files
        assert round_tripped.execution_time == pytest.approx(original.execution_time)
        assert (
            round_tripped.skipped_already_completed
            == original.skipped_already_completed
        )
        assert (
            round_tripped.skipped_active_duplicate
            == original.skipped_active_duplicate
        )
        assert round_tripped.organization_id == original.organization_id

    def test_wire_is_json_safe(self):
        wire = self._make().to_dict()
        assert json.loads(json.dumps(wire)) == wire


class TestFileExecutionResultWireShape:
    """API path (``process_file_batch_api`` returns this per-file shape)."""

    def _make_success(self) -> FileExecutionResult:
        return FileExecutionResult(
            file="invoice.pdf",
            file_execution_id="fx-1",
            status=ApiDeploymentResultStatus.SUCCESS,
            file_name="invoice.pdf",
            processing_time=4.2,
            result_data={"extracted": "value"},
            metadata={"source": "user_upload"},
        )

    def _make_failure(self) -> FileExecutionResult:
        return FileExecutionResult(
            file="broken.pdf",
            file_execution_id="fx-2",
            status=ApiDeploymentResultStatus.FAILED,
            file_name="broken.pdf",
            processing_time=0.1,
            error="extractor crashed",
        )

    def _make_skipped(self) -> FileExecutionResult:
        return FileExecutionResult(
            file="dup.pdf",
            file_execution_id="fx-3",
            status=ApiDeploymentResultStatus.SUCCESS,
            file_name="dup.pdf",
            skipped=SkipReason.ALREADY_COMPLETED,
            result_data={"cached": True},
        )

    def test_wire_carries_file_name_alias(self):
        wire = self._make_success().to_dict()
        assert wire["file_name"] == "invoice.pdf"
        assert wire["file"] == "invoice.pdf"

    def test_wire_carries_result_data_alias(self):
        wire = self._make_success().to_dict()
        assert wire["result_data"] == {"extracted": "value"}

    def test_wire_carries_skipped_marker(self):
        wire = self._make_skipped().to_dict()
        assert wire["skipped"] == SkipReason.ALREADY_COMPLETED.value

    def test_success_status_uses_canonical_vocab(self):
        wire = self._make_success().to_dict()
        assert wire["status"] == "Success"

    def test_failure_status_uses_canonical_vocab(self):
        wire = self._make_failure().to_dict()
        assert wire["status"] == "Failed"
        assert wire["error"] == "extractor crashed"

    def test_post_init_derives_status_from_error(self):
        result = FileExecutionResult(
            file="x",
            file_execution_id="fx",
            status=ApiDeploymentResultStatus.SUCCESS,
            error="boom",
        )
        assert result.status == ApiDeploymentResultStatus.FAILED

    def test_round_trip_preserves_all_aliases(self):
        original = self._make_skipped()
        round_tripped = FileExecutionResult.from_dict(original.to_dict())
        assert round_tripped.file == original.file
        assert round_tripped.file_name == original.file_name
        assert round_tripped.file_execution_id == original.file_execution_id
        assert round_tripped.result_data == original.result_data
        assert round_tripped.skipped == original.skipped
        assert round_tripped.status == original.status

    def test_active_duplicate_skip_reason_round_trips(self):
        # ``ACTIVE_DUPLICATE`` mirrors the batch-level
        # ``skipped_active_duplicate`` counter; no producer emits it
        # per-file today but the enum value must exist and round-trip
        # cleanly so a future producer can pick it without re-typing
        # the bare string.
        original = FileExecutionResult(
            file="dup.pdf",
            file_execution_id="fx",
            status=ApiDeploymentResultStatus.SUCCESS,
            skipped=SkipReason.ACTIVE_DUPLICATE,
        )
        wire = original.to_dict()
        assert wire["skipped"] == SkipReason.ACTIVE_DUPLICATE.value
        assert wire["skipped"] == "active_duplicate"
        round_tripped = FileExecutionResult.from_dict(wire)
        assert round_tripped.skipped == SkipReason.ACTIVE_DUPLICATE

    def test_wire_is_json_safe(self):
        for builder in (self._make_success, self._make_failure, self._make_skipped):
            wire = builder().to_dict()
            assert json.loads(json.dumps(wire)) == wire

    def test_none_valued_optional_fields_stripped_from_wire(self):
        """``None`` defaults are stripped both standalone AND when
        nested inside ``BatchExecutionResult.file_results``.

        ``serialize_dataclass_to_dict`` only filters ``None`` at the
        outermost level; ``BatchExecutionResult.to_dict`` adds a
        secondary filter so the per-file shape stays symmetric. Without
        that fixup a consumer doing ``"x" in result`` membership checks
        would behave differently for a standalone wire vs one read out
        of ``batch["file_results"][i]``.
        """
        minimal = FileExecutionResult(
            file="a.pdf",
            file_execution_id="fx",
            status=ApiDeploymentResultStatus.SUCCESS,
        )

        # ---- Standalone wire ----
        wire = minimal.to_dict()
        # Required fields and zero-valued numerics survive.
        assert wire["file"] == "a.pdf"
        assert wire["status"] == "Success"
        assert wire["processing_time"] == pytest.approx(0.0)
        assert wire["file_size"] == 0
        # None defaults are dropped — not in the wire dict at all.
        absent_keys = (
            "error", "result", "metadata", "file_name",
            "result_data", "skipped", "storage_result",
        )
        for absent in absent_keys:
            assert absent not in wire, f"expected {absent!r} to be stripped when None"

        # ---- Same shape when nested inside a batch ----
        batch_wire = BatchExecutionResult(
            total_files=1,
            successful_files=1,
            failed_files=0,
            execution_time=0.0,
            file_results=[minimal],
        ).to_dict()
        nested_wire = batch_wire["file_results"][0]
        for absent in absent_keys:
            assert absent not in nested_wire, (
                f"{absent!r} leaked into nested file_results wire"
            )
        assert sorted(wire.keys()) == sorted(nested_wire.keys())


class TestProducerBinding:
    """Drives the real producer functions in ``file_processing.tasks``.

    A revert at any of these sites back to a hand-rolled dict (or to
    the legacy lowercase status strings) keeps the *dataclass* tests
    green — these tests catch that by asserting the actual wire shape
    the chord callback receives from the producer.
    """

    def test_compile_batch_result_returns_typed_wire(self):
        from file_processing.tasks import _compile_batch_result

        # Minimum fake context — _compile_batch_result reads only
        # ``metadata["result"]`` (with attribute access), the two
        # skipped lists, and ``organization_context.organization_id``.
        result = SimpleNamespace(
            successful_files=4, failed_files=1, execution_time=2.5
        )
        context = SimpleNamespace(
            metadata={
                "result": result,
                "workflow_logger": None,  # avoids the publish call
                "skipped_already_completed": ["a.pdf"],
                "skipped_active_duplicate": [],
            },
            organization_context=SimpleNamespace(organization_id="org-prod"),
        )

        wire = _compile_batch_result(context)

        # Producer must emit the typed shape, not a hand-rolled dict.
        assert wire["total_files"] == 6  # 4 + 1 + 1 skipped
        assert wire["successful_files"] == 4
        assert wire["failed_files"] == 1
        assert wire["execution_time"] == pytest.approx(2.5)
        assert wire["skipped_already_completed"] == 1
        assert wire["skipped_active_duplicate"] == 0
        assert wire["organization_id"] == "org-prod"
        # Dataclass shape gains these defaults — strictly additive.
        assert wire["file_results"] == []
        assert wire["errors"] == []

    def test_process_single_file_api_already_completed_branch(self):
        from file_processing.tasks import _process_single_file_api
        from unstract.core.data_models import ExecutionStatus

        api_client = MagicMock()
        api_client.get_workflow_file_execution.return_value = SimpleNamespace(
            status=ExecutionStatus.COMPLETED.value,
            result={"cached": "value"},
            metadata={"src": "history"},
        )
        wire = _process_single_file_api(
            api_client=api_client,
            file_data={"id": "fx-1", "file_name": "doc.pdf"},
            workflow_id="wf-1",
            execution_id="exec-1",
            pipeline_id=None,
            use_file_history=True,
        )

        # Canonical per-file status vocabulary — not the legacy
        # lowercase "completed".
        assert wire["status"] == "Success"
        assert wire["skipped"] == SkipReason.ALREADY_COMPLETED.value
        assert wire["file_name"] == "doc.pdf"
        assert wire["file_execution_id"] == "fx-1"
        # Cached result + metadata propagate so the API consumer can
        # short-circuit on the historical extraction.
        assert wire["result_data"] == {"cached": "value"}
        assert wire["metadata"] == {"src": "history"}
        # Producer doesn't set ``error`` → __post_init__ keeps SUCCESS;
        # serializer strips the None.
        assert "error" not in wire

    def test_process_single_file_api_success_branch(self, monkeypatch):
        """Drives the happy-path producer. Catches reverts to the
        legacy dict-spread that dropped ``storage_result`` at the
        chord-callback boundary (silent data loss on the API path).
        """
        from file_processing import tasks as tasks_mod
        from unstract.core.data_models import ExecutionStatus

        api_client = MagicMock()
        # Not already-completed → fall through to the runner branch.
        api_client.get_workflow_file_execution.return_value = SimpleNamespace(
            status=ExecutionStatus.PENDING.value
        )
        api_client.get_workflow_definition.return_value = {"id": "wf-1"}
        api_client.get_file_content.return_value = b"hello world"
        api_client.store_file_execution_result.return_value = {
            "stored_at": "s3://bucket/key"
        }
        # Patch the runner-service call — its body shells out and isn't
        # under test here.
        monkeypatch.setattr(
            tasks_mod,
            "_call_runner_service",
            lambda **kwargs: {"extracted": "value"},
        )

        wire = tasks_mod._process_single_file_api(
            api_client=api_client,
            file_data={"id": "fx-ok", "file_name": "ok.pdf"},
            workflow_id="wf-1",
            execution_id="exec-1",
            pipeline_id=None,
            use_file_history=False,
        )

        # Canonical per-file vocabulary — not the legacy lowercase
        # ``"completed"`` the pre-typing producer used to emit.
        assert wire["status"] == "Success"
        assert wire["file_name"] == "ok.pdf"
        assert wire["file_execution_id"] == "fx-ok"
        assert wire["result_data"] == {"extracted": "value"}
        # The whole point of this test: ``storage_result`` must survive
        # the typed dataclass round-trip (UN-3513 finding).
        assert wire["storage_result"] == {"stored_at": "s3://bucket/key"}
        # No error → success branch keeps SUCCESS; ``error`` stripped.
        assert "error" not in wire
        assert "skipped" not in wire

    def test_process_single_file_api_failure_branch(self, monkeypatch):
        """Drives the except-block producer. Catches reverts to the
        legacy lowercase ``"failed"`` status string.
        """
        from file_processing import tasks as tasks_mod
        from unstract.core.data_models import ExecutionStatus

        api_client = MagicMock()
        api_client.get_workflow_file_execution.return_value = SimpleNamespace(
            status=ExecutionStatus.PENDING.value
        )
        api_client.get_workflow_definition.return_value = {"id": "wf-1"}
        api_client.get_file_content.return_value = b"payload"
        # Runner blows up → producer falls into the except branch.
        monkeypatch.setattr(
            tasks_mod,
            "_call_runner_service",
            MagicMock(side_effect=RuntimeError("runner crashed")),
        )

        wire = tasks_mod._process_single_file_api(
            api_client=api_client,
            file_data={"id": "fx-bad", "file_name": "bad.pdf"},
            workflow_id="wf-1",
            execution_id="exec-1",
            pipeline_id=None,
            use_file_history=False,
        )

        assert wire["status"] == "Failed"
        assert wire["file_name"] == "bad.pdf"
        assert wire["file_execution_id"] == "fx-bad"
        assert wire["error"] == "runner crashed"
        # Failure branch carries no result/storage payload.
        assert "result_data" not in wire
        assert "storage_result" not in wire

    def test_process_file_batch_api_batch_wrapper(self, monkeypatch):
        """Drives the API-path batch wrapper. Catches reverts at the
        ``BatchExecutionResult(...).to_dict()`` producer site
        (file_processing/tasks.py around L1665).
        """
        from file_processing import tasks as tasks_mod
        from file_processing.worker import app as celery_app

        # Swap postgres result backend for in-memory so ``.apply()``
        # doesn't try to persist the eager task result.
        original = {
            "task_always_eager": celery_app.conf.task_always_eager,
            "task_eager_propagates": celery_app.conf.task_eager_propagates,
            "result_backend": celery_app.conf.result_backend,
        }
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            result_backend="cache+memory://",
        )

        # Stub per-file producer with two typed file results — one
        # already-completed skip, one fresh success.
        skipped_wire = FileExecutionResult(
            file="a.pdf",
            file_execution_id="fx-a",
            status=ApiDeploymentResultStatus.SUCCESS,
            file_name="a.pdf",
            result_data={"cached": True},
            skipped=SkipReason.ALREADY_COMPLETED,
        ).to_dict()
        ok_wire = FileExecutionResult(
            file="b.pdf",
            file_execution_id="fx-b",
            status=ApiDeploymentResultStatus.SUCCESS,
            file_name="b.pdf",
            result_data={"extracted": "value"},
            storage_result={"stored": "s3://k"},
        ).to_dict()
        per_file_outputs = iter([skipped_wire, ok_wire])

        monkeypatch.setattr(
            tasks_mod,
            "_process_single_file_api",
            lambda **kwargs: next(per_file_outputs),
        )
        # Neutralise organisation-level side effects.
        monkeypatch.setattr(
            tasks_mod.StateStore, "set", lambda *a, **k: None
        )
        api_client_stub = MagicMock()
        api_client_stub.get_workflow_execution.return_value = SimpleNamespace(
            success=True, data={"execution": {"execution_log_id": None}}
        )
        monkeypatch.setattr(
            tasks_mod, "create_api_client", lambda schema_name: api_client_stub
        )
        # ``WorkerWorkflowExecutionService`` is imported inline inside
        # the batch task; patch the lazy import path.
        cache_service = MagicMock()
        cache_service.return_value.cache_api_result = MagicMock()
        import shared.workflow.execution.service as service_mod

        monkeypatch.setattr(
            service_mod, "WorkerWorkflowExecutionService", cache_service
        )

        try:
            wire = tasks_mod.process_file_batch_api.apply(
                args=[
                    "org-1",  # schema_name
                    "wf-1",  # workflow_id
                    "exec-1",  # execution_id
                    "batch-1",  # batch_id
                    [
                        {"id": "fx-a", "file_name": "a.pdf"},
                        {"id": "fx-b", "file_name": "b.pdf"},
                    ],  # created_files
                    None,  # pipeline_id
                    None,  # execution_mode
                    False,  # use_file_history
                ]
            ).get()
        finally:
            celery_app.conf.update(original)

        # Producer must emit the typed BatchExecutionResult shape.
        assert wire["total_files"] == 2
        # Legacy API-path semantic: skipped files count as successful.
        assert wire["successful_files"] == 2
        assert wire["failed_files"] == 0
        # Skip counter derived from SkipReason.ALREADY_COMPLETED.value
        # — a typo here would silently zero the counter.
        assert wire["skipped_already_completed"] == 1
        assert wire["organization_id"] == "org-1"
        # ``execution_time`` is a required positional on the dataclass;
        # omitting it would crash the task at the producer site.
        assert "execution_time" in wire
        assert wire["execution_time"] >= 0.0
        # file_results round-trips through FileExecutionResult, so
        # ``storage_result`` survives to the batch boundary.
        stored = [
            fr
            for fr in wire["file_results"]
            if fr.get("file_execution_id") == "fx-b"
        ]
        assert stored and stored[0]["storage_result"] == {"stored": "s3://k"}


class TestRealConsumerTolerance:
    """Drives the real ``aggregate_file_batch_results`` against the
    new wire shape — proves the producer-consumer contract end-to-end.
    """

    def test_aggregator_consumes_general_path_shape(self):
        wire = BatchExecutionResult(
            total_files=5,
            successful_files=4,
            failed_files=1,
            execution_time=2.0,
            skipped_already_completed=0,
            skipped_active_duplicate=0,
            organization_id="org-1",
        ).to_dict()

        aggregated = aggregate_file_batch_results([wire])

        assert aggregated["total_files"] == 5
        assert aggregated["successful_files"] == 4
        assert aggregated["failed_files"] == 1
        assert aggregated["batches_processed"] == 1

    def test_aggregator_consumes_multi_batch(self):
        batches = [
            BatchExecutionResult(
                total_files=3,
                successful_files=3,
                failed_files=0,
                execution_time=1.0,
            ).to_dict(),
            BatchExecutionResult(
                total_files=2,
                successful_files=1,
                failed_files=1,
                execution_time=0.5,
            ).to_dict(),
        ]
        aggregated = aggregate_file_batch_results(batches)
        assert aggregated["total_files"] == 5
        assert aggregated["successful_files"] == 4
        assert aggregated["failed_files"] == 1
        assert aggregated["batches_processed"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
