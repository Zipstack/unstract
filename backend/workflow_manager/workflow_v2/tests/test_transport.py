"""Tests for the 9e transport-resolution seam (PR 3 — Flipt canary wiring).

``resolve_transport`` is the single chokepoint that decides whether a new
execution rides the legacy Celery transport or the Postgres queue. It is gated
by an env master-switch and, when that is on, by a Flipt boolean flag; it fails
closed to Celery on any problem. These tests pin that contract.
"""

from unittest.mock import MagicMock, patch

from django.test import override_settings
from unstract.core.data_models import (
    DEFAULT_WORKFLOW_TRANSPORT,
    WorkflowTransport,
    normalize_transport,
)

from workflow_manager.workflow_v2.transport import (
    PG_QUEUE_FLAG_KEY,
    resolve_transport,
)

# Where ``check_feature_flag_status`` is looked up (imported into the module).
_FLIPT = "workflow_manager.workflow_v2.transport.check_feature_flag_status"


class TestWorkflowTransportEnum:
    def test_values(self):
        assert WorkflowTransport.CELERY.value == "celery"
        assert WorkflowTransport.PG_QUEUE.value == "pg_queue"

    def test_default_is_celery(self):
        assert DEFAULT_WORKFLOW_TRANSPORT == WorkflowTransport.CELERY.value


class TestResolveTransport:
    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=False)
    def test_master_gate_off_never_consults_flipt(self):
        """Master-gate off → Celery, and Flipt is not even called."""
        with patch(_FLIPT) as flipt:
            result = resolve_transport(execution_id="e1", organization_id="org1")
        assert result == WorkflowTransport.CELERY.value
        flipt.assert_not_called()

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_gate_on_flipt_true_resolves_pg_queue(self):
        with patch(_FLIPT, return_value=True):
            result = resolve_transport(execution_id="e1", organization_id="org1")
        assert result == WorkflowTransport.PG_QUEUE.value

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_gate_on_flipt_false_resolves_celery(self):
        with patch(_FLIPT, return_value=False):
            result = resolve_transport(execution_id="e1", organization_id="org1")
        assert result == WorkflowTransport.CELERY.value

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_flipt_exception_fails_closed_to_celery(self):
        """A Flipt outage must never break execution creation."""
        with patch(_FLIPT, side_effect=RuntimeError("flipt down")):
            result = resolve_transport(execution_id="e1", organization_id="org1")
        assert result == WorkflowTransport.CELERY.value

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_passes_execution_id_as_entity_and_builds_context(self):
        """entity_id = execution_id (sticky bucketing); context carries the
        org/workflow/pipeline for segment rules.
        """
        with patch(_FLIPT, return_value=True) as flipt:
            resolve_transport(
                execution_id="exec-42",
                organization_id="org1",
                workflow_id="wf1",
                pipeline_id="pl1",
            )
        flipt.assert_called_once_with(
            flag_key=PG_QUEUE_FLAG_KEY,
            entity_id="exec-42",
            context={
                "organization_id": "org1",
                "workflow_id": "wf1",
                "pipeline_id": "pl1",
            },
        )

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_non_string_ids_are_coerced_for_flipt(self):
        """Callers pass UUID objects for the ids. Flipt's context is a gRPC
        map<string,string> and entity_id must hash stably, so every value must
        reach check_feature_flag_status as a plain str — otherwise the client
        swallows the serialization error as False and silently forces celery.
        Regression test for that exact dev-test finding.
        """
        import uuid

        ex = uuid.UUID("8c091789-9dde-45e7-bb85-06f23fe120eb")
        wf = uuid.UUID("ebed2834-c9fb-4b6c-8df3-9dd841f616bb")
        pl = uuid.UUID("eaca3b0e-083a-4c75-8b25-85349d54145b")
        with patch(_FLIPT, return_value=True) as flipt:
            result = resolve_transport(
                execution_id=ex, organization_id="org1", workflow_id=wf, pipeline_id=pl
            )
        assert result == WorkflowTransport.PG_QUEUE.value
        _, kwargs = flipt.call_args
        assert kwargs["entity_id"] == str(ex)
        assert all(isinstance(v, str) for v in kwargs["context"].values())
        assert kwargs["context"]["workflow_id"] == str(wf)
        assert kwargs["context"]["pipeline_id"] == str(pl)

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_context_omits_unset_optional_ids(self):
        with patch(_FLIPT, return_value=True) as flipt:
            resolve_transport(execution_id="exec-42", organization_id="org1")
        _, kwargs = flipt.call_args
        assert kwargs["context"] == {"organization_id": "org1"}

    @override_settings(PG_QUEUE_TRANSPORT_ENABLED=True)
    def test_result_is_a_valid_transport_value(self):
        valid = {t.value for t in WorkflowTransport}
        with patch(_FLIPT, return_value=True):
            assert (
                resolve_transport(execution_id="e1", organization_id="org1") in valid
            )


class TestNormalizeTransport:
    """The fail-closed coercion used at every untrusted read boundary."""

    def test_recognized_values_pass_through(self):
        assert normalize_transport("celery") == "celery"
        assert normalize_transport("pg_queue") == "pg_queue"

    def test_unrecognized_value_falls_back_to_celery(self):
        assert normalize_transport("celary") == DEFAULT_WORKFLOW_TRANSPORT
        assert normalize_transport("pg-queue") == DEFAULT_WORKFLOW_TRANSPORT

    def test_none_and_empty_fall_back_to_celery(self):
        assert normalize_transport(None) == DEFAULT_WORKFLOW_TRANSPORT
        assert normalize_transport("") == DEFAULT_WORKFLOW_TRANSPORT

    def test_invalid_value_logs_a_warning_when_logger_given(self):
        log = MagicMock()
        assert normalize_transport("bogus", logger=log, context=" [exec:x]") == "celery"
        log.warning.assert_called_once()

    def test_valid_value_does_not_warn(self):
        log = MagicMock()
        normalize_transport("pg_queue", logger=log)
        log.warning.assert_not_called()
