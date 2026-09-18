"""Gating tests for the UN-4078 rolling-deploy shim.

Nothing reads the ``transport`` key after UN-4078, so only a test stops it being
dropped before the follow-up release — and dropping it strands executions that a
pre-UN-4078 worker picks up during a rolling deploy (it defaults an absent field
to "celery" and publishes to a broker with no consumers).

These must run in the DEFAULT lane: the ``PgBarrier.enqueue`` tests that also
cover the descriptor need a real Postgres and are skipped wherever one is absent,
so they cannot be the only guard. Delete this file with the shim's writes.
"""

from unstract.core.data_models import LEGACY_TRANSPORT_KEY, LEGACY_TRANSPORT_VALUE

from queue_backend.pg_barrier import build_callback_descriptor


class TestCallbackDescriptorShim:
    def _descriptor(self):
        return build_callback_descriptor(
            task_name="process_batch_callback",
            kwargs={"execution_id": "exec-1", "organization_id": "org-1"},
            queue="file_processing_callback",
            fairness_headers=None,
        )

    def test_descriptor_carries_the_transport_shim(self):
        # A pre-UN-4078 consumer reads callback_descriptor.get("transport") and
        # fires the callback through Celery when it is missing.
        assert self._descriptor()[LEGACY_TRANSPORT_KEY] == LEGACY_TRANSPORT_VALUE

    def test_shim_value_is_never_celery(self):
        # "celery" is the one value that must never be written: it selects the
        # dead transport explicitly rather than by omission.
        assert self._descriptor()[LEGACY_TRANSPORT_KEY] == "pg_queue"

    def test_descriptor_keeps_its_other_wire_keys(self):
        d = self._descriptor()
        assert d["task_name"] == "process_batch_callback"
        assert d["queue"] == "file_processing_callback"
        assert d["kwargs"]["execution_id"] == "exec-1"
        assert d["fairness_headers"] is None
