"""
Tests for Audit Logger implementation.

This module tests the AuditLogger class including logging executions,
convenience methods, and statistics retrieval.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from lookup.services.audit_logger import AuditLogger


class TestAuditLogger:
    """Test cases for AuditLogger class."""

    @pytest.fixture
    def audit_logger(self):
        """Create an AuditLogger instance."""
        return AuditLogger()

    @pytest.fixture
    def mock_project(self):
        """Create a mock LookupProject."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "Test Look-Up"
        return project

    @pytest.fixture
    def execution_params(self, mock_project):
        """Create standard execution parameters."""
        return {
            'execution_id': str(uuid.uuid4()),
            'lookup_project_id': mock_project.id,
            'prompt_studio_project_id': uuid.uuid4(),
            'input_data': {'vendor': 'Slack Technologies'},
            'reference_data_version': 2,
            'llm_provider': 'openai',
            'llm_model': 'gpt-4',
            'llm_prompt': 'Match vendor Slack Technologies...',
            'llm_response': '{"canonical_vendor": "Slack", "confidence": 0.92}',
            'enriched_output': {'canonical_vendor': 'Slack'},
            'status': 'success',
            'confidence_score': 0.92,
            'execution_time_ms': 1234,
            'llm_call_time_ms': 890,
            'llm_response_cached': False,
            'error_message': None
        }

    # ========== Basic Logging Tests ==========

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_successful_logging(
        self, mock_project_model, mock_audit_model,
        audit_logger, execution_params, mock_project
    ):
        """Test successful execution logging."""
        # Setup mocks
        mock_project_model.objects.get.return_value = mock_project
        mock_audit_instance = MagicMock()
        mock_audit_instance.id = uuid.uuid4()
        mock_audit_model.objects.create.return_value = mock_audit_instance

        # Log execution
        result = audit_logger.log_execution(**execution_params)

        # Verify project was fetched
        mock_project_model.objects.get.assert_called_once_with(
            id=execution_params['lookup_project_id']
        )

        # Verify audit was created with correct params
        mock_audit_model.objects.create.assert_called_once()
        create_call = mock_audit_model.objects.create.call_args
        kwargs = create_call.kwargs

        assert kwargs['lookup_project'] == mock_project
        assert kwargs['execution_id'] == execution_params['execution_id']
        assert kwargs['status'] == 'success'
        assert kwargs['llm_provider'] == 'openai'
        assert kwargs['llm_model'] == 'gpt-4'
        assert kwargs['confidence_score'] == Decimal('0.92')

        # Verify return value
        assert result == mock_audit_instance

    @patch('lookup.services.audit_logger.LookupProject')
    def test_project_not_found(
        self, mock_project_model, audit_logger, execution_params
    ):
        """Test handling when Look-Up project doesn't exist."""
        # Make project lookup fail
        mock_project_model.objects.get.side_effect = mock_project_model.DoesNotExist()

        # Log execution
        result = audit_logger.log_execution(**execution_params)

        # Should return None and not raise exception
        assert result is None

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_database_error_handling(
        self, mock_project_model, mock_audit_model,
        audit_logger, execution_params, mock_project
    ):
        """Test handling of database errors during logging."""
        # Setup mocks
        mock_project_model.objects.get.return_value = mock_project
        mock_audit_model.objects.create.side_effect = Exception("Database error")

        # Log execution - should not raise exception
        result = audit_logger.log_execution(**execution_params)

        # Should return None
        assert result is None

    # ========== Convenience Method Tests ==========

    @patch('lookup.services.audit_logger.AuditLogger.log_execution')
    def test_log_success(self, mock_log_execution, audit_logger):
        """Test log_success convenience method."""
        execution_id = str(uuid.uuid4())
        project_id = uuid.uuid4()

        audit_logger.log_success(
            execution_id=execution_id,
            project_id=project_id,
            input_data={'test': 'data'},
            confidence_score=0.85
        )

        mock_log_execution.assert_called_once_with(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status='success',
            input_data={'test': 'data'},
            confidence_score=0.85
        )

    @patch('lookup.services.audit_logger.AuditLogger.log_execution')
    def test_log_failure(self, mock_log_execution, audit_logger):
        """Test log_failure convenience method."""
        execution_id = str(uuid.uuid4())
        project_id = uuid.uuid4()
        error_msg = "LLM timeout"

        audit_logger.log_failure(
            execution_id=execution_id,
            project_id=project_id,
            error=error_msg,
            input_data={'test': 'data'}
        )

        mock_log_execution.assert_called_once_with(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status='failed',
            error_message=error_msg,
            input_data={'test': 'data'}
        )

    @patch('lookup.services.audit_logger.AuditLogger.log_execution')
    def test_log_partial(self, mock_log_execution, audit_logger):
        """Test log_partial convenience method."""
        execution_id = str(uuid.uuid4())
        project_id = uuid.uuid4()

        audit_logger.log_partial(
            execution_id=execution_id,
            project_id=project_id,
            confidence_score=0.35,
            error_message='Low confidence'
        )

        mock_log_execution.assert_called_once_with(
            execution_id=execution_id,
            lookup_project_id=project_id,
            status='partial',
            confidence_score=0.35,
            error_message='Low confidence'
        )

    # ========== Data Validation Tests ==========

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_confidence_score_conversion(
        self, mock_project_model, mock_audit_model,
        audit_logger, execution_params, mock_project
    ):
        """Test that confidence score is properly converted to Decimal."""
        mock_project_model.objects.get.return_value = mock_project
        mock_audit_model.objects.create.return_value = MagicMock()

        # Test with float confidence
        execution_params['confidence_score'] = 0.456789
        audit_logger.log_execution(**execution_params)

        create_call = mock_audit_model.objects.create.call_args
        assert create_call.kwargs['confidence_score'] == Decimal('0.456789')

        # Test with None confidence
        execution_params['confidence_score'] = None
        audit_logger.log_execution(**execution_params)

        create_call = mock_audit_model.objects.create.call_args
        assert create_call.kwargs['confidence_score'] is None

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_optional_fields(
        self, mock_project_model, mock_audit_model,
        audit_logger, mock_project
    ):
        """Test logging with minimal required fields."""
        mock_project_model.objects.get.return_value = mock_project
        mock_audit_model.objects.create.return_value = MagicMock()

        # Minimal parameters
        minimal_params = {
            'execution_id': str(uuid.uuid4()),
            'lookup_project_id': mock_project.id,
            'prompt_studio_project_id': None,
            'input_data': {},
            'reference_data_version': 1,
            'llm_provider': 'openai',
            'llm_model': 'gpt-4',
            'llm_prompt': 'test prompt',
            'llm_response': None,
            'enriched_output': None,
            'status': 'failed'
        }

        result = audit_logger.log_execution(**minimal_params)

        # Should still create audit record
        mock_audit_model.objects.create.assert_called_once()

    # ========== History Retrieval Tests ==========

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    def test_get_execution_history(self, mock_audit_model, audit_logger):
        """Test retrieving execution history."""
        execution_id = str(uuid.uuid4())

        # Create mock audit records
        mock_audits = []
        for i in range(3):
            audit = MagicMock()
            audit.lookup_project.name = f"Look-Up {i+1}"
            audit.status = 'success' if i < 2 else 'failed'
            mock_audits.append(audit)

        # Setup mock query
        mock_queryset = MagicMock()
        mock_queryset.select_related.return_value = mock_queryset
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.__getitem__.return_value = mock_audits
        mock_audit_model.objects.filter.return_value = mock_queryset

        # Get history
        result = audit_logger.get_execution_history(execution_id, limit=10)

        # Verify query
        mock_audit_model.objects.filter.assert_called_once_with(
            execution_id=execution_id
        )
        mock_queryset.select_related.assert_called_once_with('lookup_project')
        mock_queryset.order_by.assert_called_once_with('executed_at')

        # Check result
        assert len(result) == 3
        assert result[0].status == 'success'
        assert result[2].status == 'failed'

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    def test_get_execution_history_error_handling(
        self, mock_audit_model, audit_logger
    ):
        """Test error handling in get_execution_history."""
        mock_audit_model.objects.filter.side_effect = Exception("Database error")

        result = audit_logger.get_execution_history('test-id')

        # Should return empty list on error
        assert result == []

    # ========== Statistics Tests ==========

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    def test_get_project_stats(self, mock_audit_model, audit_logger):
        """Test getting project statistics."""
        project_id = uuid.uuid4()

        # Create mock audit records
        mock_audits = []

        # 3 successful executions
        for i in range(3):
            audit = MagicMock()
            audit.status = 'success'
            audit.execution_time_ms = 1000 + i * 100
            audit.llm_response_cached = (i == 0)  # First one cached
            audit.confidence_score = Decimal(f'0.{80 + i}')
            mock_audits.append(audit)

        # 1 failed execution
        audit = MagicMock()
        audit.status = 'failed'
        audit.execution_time_ms = 500
        audit.llm_response_cached = False
        audit.confidence_score = None
        mock_audits.append(audit)

        # 1 partial execution
        audit = MagicMock()
        audit.status = 'partial'
        audit.execution_time_ms = 800
        audit.llm_response_cached = False
        audit.confidence_score = Decimal('0.40')
        mock_audits.append(audit)

        # Setup mock query
        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.__getitem__.return_value = mock_audits
        mock_audit_model.objects.filter.return_value = mock_queryset

        # Get stats
        stats = audit_logger.get_project_stats(project_id, limit=100)

        # Verify stats
        assert stats['total_executions'] == 5
        assert stats['successful'] == 3
        assert stats['failed'] == 1
        assert stats['partial'] == 1
        assert stats['success_rate'] == 0.6  # 3/5
        assert stats['cache_hit_rate'] == 0.2  # 1/5
        assert stats['avg_execution_time_ms'] == 880  # (1000+1100+1200+500+800)/5
        # avg_confidence = (0.80 + 0.81 + 0.82 + 0.40) / 4 = 0.7075
        assert abs(stats['avg_confidence'] - 0.7075) < 0.001

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    def test_get_project_stats_empty(self, mock_audit_model, audit_logger):
        """Test getting stats for project with no executions."""
        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.__getitem__.return_value = []
        mock_audit_model.objects.filter.return_value = mock_queryset

        stats = audit_logger.get_project_stats(uuid.uuid4())

        assert stats['total_executions'] == 0
        assert stats['success_rate'] == 0.0
        assert stats['avg_execution_time_ms'] == 0
        assert stats['cache_hit_rate'] == 0.0
        assert stats['avg_confidence'] == 0.0

    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    def test_get_project_stats_error_handling(
        self, mock_audit_model, audit_logger
    ):
        """Test error handling in get_project_stats."""
        mock_audit_model.objects.filter.side_effect = Exception("Database error")

        stats = audit_logger.get_project_stats(uuid.uuid4())

        # Should return zero stats on error
        assert stats['total_executions'] == 0
        assert stats['success_rate'] == 0.0

    # ========== Integration Tests ==========

    @patch('lookup.services.audit_logger.logger')
    @patch('lookup.services.audit_logger.LookupExecutionAudit')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_logging_messages(
        self, mock_project_model, mock_audit_model, mock_logger,
        audit_logger, execution_params, mock_project
    ):
        """Test that appropriate log messages are generated."""
        mock_project_model.objects.get.return_value = mock_project
        mock_audit_instance = MagicMock()
        mock_audit_instance.id = uuid.uuid4()
        mock_audit_model.objects.create.return_value = mock_audit_instance

        audit_logger.log_execution(**execution_params)

        # Should log debug message on success
        mock_logger.debug.assert_called()
        debug_message = mock_logger.debug.call_args[0][0]
        assert 'Logged execution audit' in debug_message
        assert mock_project.name in debug_message

    @patch('lookup.services.audit_logger.logger')
    @patch('lookup.services.audit_logger.LookupProject')
    def test_error_logging(
        self, mock_project_model, mock_logger,
        audit_logger, execution_params
    ):
        """Test that errors are properly logged."""
        mock_project_model.objects.get.side_effect = Exception("Database connection lost")

        audit_logger.log_execution(**execution_params)

        # Should log exception
        mock_logger.exception.assert_called()
        error_message = mock_logger.exception.call_args[0][0]
        assert 'Failed to log execution audit' in error_message

    def test_real_world_scenario(self, audit_logger):
        """Test realistic usage scenario with mock objects."""
        # This would normally require Django test database
        # For now, just verify the interface works correctly

        execution_id = str(uuid.uuid4())
        project_id = uuid.uuid4()

        # Log various execution types
        with patch('lookup.services.audit_logger.AuditLogger.log_execution') as mock_log:
            mock_log.return_value = MagicMock()

            # Success
            audit_logger.log_success(
                execution_id=execution_id,
                project_id=project_id,
                input_data={'vendor': 'Slack'},
                enriched_output={'canonical': 'Slack'},
                confidence_score=0.95
            )

            # Failure
            audit_logger.log_failure(
                execution_id=execution_id,
                project_id=project_id,
                error='Timeout',
                input_data={'vendor': 'Unknown'}
            )

            # Partial
            audit_logger.log_partial(
                execution_id=execution_id,
                project_id=project_id,
                confidence_score=0.30
            )

            # Verify all three logs were attempted
            assert mock_log.call_count == 3
