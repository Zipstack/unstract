"""Wire-shape characterisation for the chord-callback boundary.

Locks the on-wire contract for the two producer paths that feed
``process_batch_callback`` (general path) and ``process_batch_callback_api``
(API path). Producers now build typed dataclasses and serialise via
``.to_dict()``; these tests assert the resulting dicts contain every
field the consumer reads, plus the strictly-additive ones the dataclass
schema introduces.
"""

from __future__ import annotations

import json

import pytest

from unstract.core.worker_models import (
    ApiDeploymentResultStatus,
    BatchExecutionResult,
    FileExecutionResult,
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
        # ``aggregate_file_batch_results`` reads these via ``.get()`` —
        # they must appear in the wire dict so the existing consumer
        # behaviour is preserved.
        wire = self._make().to_dict()
        for key in (
            "total_files",
            "successful_files",
            "failed_files",
            "execution_time",
            "file_results",  # consumer iterates this; empty list by default
        ):
            assert key in wire, f"consumer-read field missing: {key}"

    def test_wire_carries_extended_optional_fields(self):
        wire = self._make().to_dict()
        # These three are the strictly-additive fields the Phase 5.3
        # extension introduced. Producer populates; legacy consumers
        # that don't know about them are unaffected.
        assert wire["skipped_already_completed"] == 1
        assert wire["skipped_active_duplicate"] == 0
        assert wire["organization_id"] == "org-test"

    def test_round_trip_preserves_all_fields(self):
        original = self._make()
        round_tripped = BatchExecutionResult.from_dict(original.to_dict())
        assert round_tripped.total_files == original.total_files
        assert round_tripped.successful_files == original.successful_files
        assert round_tripped.failed_files == original.failed_files
        assert round_tripped.execution_time == original.execution_time
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
        # Celery's default serializer is JSON — the dict must round-trip
        # through ``json.dumps`` / ``json.loads`` without loss.
        wire = self._make().to_dict()
        assert json.loads(json.dumps(wire)) == wire

    def test_defaults_safe_when_no_skips(self):
        result = BatchExecutionResult(
            total_files=3,
            successful_files=3,
            failed_files=0,
            execution_time=1.0,
        )
        wire = result.to_dict()
        assert wire["skipped_already_completed"] == 0
        assert wire["skipped_active_duplicate"] == 0


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
            skipped="already_completed",
            result_data={"cached": True},
        )

    def test_wire_carries_file_name_alias(self):
        # The API path's legacy wire uses ``file_name`` (not ``file``);
        # the dataclass preserves the alias.
        wire = self._make_success().to_dict()
        assert wire["file_name"] == "invoice.pdf"
        assert wire["file"] == "invoice.pdf"  # canonical alongside legacy

    def test_wire_carries_result_data_alias(self):
        wire = self._make_success().to_dict()
        assert wire["result_data"] == {"extracted": "value"}

    def test_wire_carries_skipped_marker(self):
        wire = self._make_skipped().to_dict()
        assert wire["skipped"] == "already_completed"

    def test_success_status_uses_canonical_vocab(self):
        # Domain correction: per-file results use ``ApiDeploymentResultStatus``
        # vocabulary (Success / Failed), not the ad-hoc lowercase
        # "completed" / "failed" that the legacy dict producer used.
        wire = self._make_success().to_dict()
        assert wire["status"] == "Success"

    def test_failure_status_uses_canonical_vocab(self):
        wire = self._make_failure().to_dict()
        assert wire["status"] == "Failed"
        assert wire["error"] == "extractor crashed"

    def test_post_init_derives_status_from_error(self):
        # An error string forces FAILED regardless of the status passed
        # to the constructor.
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

    def test_wire_is_json_safe(self):
        for builder in (self._make_success, self._make_failure, self._make_skipped):
            wire = builder().to_dict()
            assert json.loads(json.dumps(wire)) == wire


class TestConsumerTolerance:
    """The chord-callback consumer (``aggregate_file_batch_results``)
    reads via ``.get(..., default)``. Verifies the new wire shape
    doesn't omit any field the consumer relies on."""

    def test_aggregator_can_read_general_path_shape(self):
        wire = BatchExecutionResult(
            total_files=5,
            successful_files=4,
            failed_files=1,
            execution_time=2.0,
            skipped_already_completed=0,
            skipped_active_duplicate=0,
            organization_id="org-1",
        ).to_dict()
        # Mirrors aggregate_file_batch_results' ``.get()`` reads.
        assert wire.get("total_files", 0) == 5
        assert wire.get("successful_files", 0) == 4
        assert wire.get("failed_files", 0) == 1
        assert wire.get("execution_time", 0) == 2.0
        # ``file_results`` is read (default []), and ``skipped_files``
        # is read but never written — same as legacy behaviour.
        assert wire.get("file_results", []) == []
        assert wire.get("skipped_files", 0) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
