"""
Tests for Look-Up Orchestrator implementation.

This module tests the LookUpOrchestrator class including parallel execution,
timeout handling, result merging, and error recovery.
"""

import time
import uuid
from concurrent.futures import TimeoutError as FutureTimeoutError
from unittest.mock import MagicMock, patch

import pytest

from lookup.services.lookup_orchestrator import LookUpOrchestrator


class TestLookUpOrchestrator:
    """Test cases for LookUpOrchestrator class."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock LookUpExecutor."""
        executor = MagicMock()
        # Default to successful execution
        executor.execute.return_value = {
            'status': 'success',
            'project_id': uuid.uuid4(),
            'project_name': 'Test Look-Up',
            'data': {'field': 'value'},
            'confidence': 0.9,
            'cached': False,
            'execution_time_ms': 100
        }
        return executor

    @pytest.fixture
    def mock_merger(self):
        """Create a mock EnrichmentMerger."""
        merger = MagicMock()
        merger.merge.return_value = {
            'data': {'merged_field': 'merged_value'},
            'conflicts_resolved': 0,
            'enrichment_details': []
        }
        return merger

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            'max_concurrent_executions': 5,
            'queue_timeout_seconds': 10,
            'execution_timeout_seconds': 2
        }

    @pytest.fixture
    def orchestrator(self, mock_executor, mock_merger, config):
        """Create a LookUpOrchestrator with mocked dependencies."""
        return LookUpOrchestrator(
            executor=mock_executor,
            merger=mock_merger,
            config=config
        )

    @pytest.fixture
    def sample_input_data(self):
        """Create sample input data."""
        return {
            'vendor': 'Slack Technologies',
            'amount': 5000
        }

    @pytest.fixture
    def mock_projects(self):
        """Create mock Look-Up projects."""
        projects = []
        for i in range(3):
            project = MagicMock()
            project.id = uuid.uuid4()
            project.name = f"Look-Up {i+1}"
            projects.append(project)
        return projects

    # ========== Basic Execution Tests ==========

    def test_successful_parallel_execution(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor, mock_merger
    ):
        """Test successful parallel execution of multiple Look-Ups."""
        # Setup executor to return different data for each project
        def execute_side_effect(project, input_data):
            return {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {f'field_{project.name}': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 100
            }

        mock_executor.execute.side_effect = execute_side_effect

        # Execute
        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Verify execution
        assert mock_executor.execute.call_count == 3
        assert mock_merger.merge.call_count == 1

        # Check metadata
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 3
        assert metadata['lookups_successful'] == 3
        assert metadata['lookups_failed'] == 0
        assert 'execution_id' in metadata
        assert 'executed_at' in metadata
        assert metadata['total_execution_time_ms'] > 0

    def test_empty_projects_list(self, orchestrator, sample_input_data):
        """Test execution with empty projects list."""
        result = orchestrator.execute_lookups(sample_input_data, [])

        assert result['lookup_enrichment'] == {}
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 0
        assert metadata['lookups_successful'] == 0
        assert metadata['lookups_failed'] == 0
        assert metadata['enrichments'] == []

    def test_single_project_execution(
        self, orchestrator, sample_input_data, mock_executor
    ):
        """Test execution with single Look-Up project."""
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "Single Look-Up"

        result = orchestrator.execute_lookups(sample_input_data, [project])

        assert mock_executor.execute.call_count == 1
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 1
        assert metadata['lookups_successful'] == 1

    # ========== Failure Handling Tests ==========

    def test_partial_failures(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor, mock_merger
    ):
        """Test handling of partial failures."""
        # Setup: First succeeds, second fails, third succeeds
        def execute_side_effect(project, input_data):
            if project.name == "Look-Up 2":
                return {
                    'status': 'failed',
                    'project_id': project.id,
                    'project_name': project.name,
                    'error': 'Test error',
                    'execution_time_ms': 50,
                    'cached': False
                }
            return {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {'field': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 100
            }

        mock_executor.execute.side_effect = execute_side_effect

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Check results
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 3
        assert metadata['lookups_successful'] == 2
        assert metadata['lookups_failed'] == 1

        # Verify merger was called with only successful enrichments
        merge_call_args = mock_merger.merge.call_args[0][0]
        assert len(merge_call_args) == 2  # Only successful ones

    def test_all_failures(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor, mock_merger
    ):
        """Test handling when all Look-Ups fail."""
        mock_executor.execute.return_value = {
            'status': 'failed',
            'project_id': uuid.uuid4(),
            'project_name': 'Failed Look-Up',
            'error': 'Test error',
            'execution_time_ms': 50,
            'cached': False
        }

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Check results
        assert result['lookup_enrichment'] == {}  # Empty merged data
        metadata = result['_lookup_metadata']
        assert metadata['lookups_successful'] == 0
        assert metadata['lookups_failed'] == 3
        assert metadata['conflicts_resolved'] == 0

    # ========== Timeout Tests ==========

    @patch('lookup.services.lookup_orchestrator.ThreadPoolExecutor')
    def test_individual_execution_timeout(
        self, mock_executor_class, orchestrator, sample_input_data,
        mock_projects
    ):
        """Test handling of individual execution timeouts."""
        # Setup mock executor
        mock_thread_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_thread_executor

        # Create futures that will timeout
        future1 = MagicMock()
        future1.result.side_effect = FutureTimeoutError()

        future2 = MagicMock()
        future2.result.return_value = {
            'status': 'success',
            'project_id': mock_projects[1].id,
            'project_name': mock_projects[1].name,
            'data': {'field': 'value'},
            'confidence': 0.9,
            'cached': False,
            'execution_time_ms': 100
        }

        # Setup as_completed to return futures
        with patch('lookup.services.lookup_orchestrator.as_completed') as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]

            # Setup submit to return futures
            mock_thread_executor.submit.side_effect = [future1, future2, MagicMock()]

            result = orchestrator.execute_lookups(sample_input_data, mock_projects[:2])

            metadata = result['_lookup_metadata']
            # One timeout (failed), one success
            assert metadata['lookups_failed'] >= 1
            assert metadata['lookups_successful'] >= 1

    @patch('lookup.services.lookup_orchestrator.as_completed')
    def test_queue_timeout(
        self, mock_as_completed, orchestrator, sample_input_data,
        mock_projects
    ):
        """Test handling of overall queue timeout."""
        # Make as_completed raise TimeoutError
        mock_as_completed.side_effect = FutureTimeoutError()

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 3
        assert metadata['lookups_successful'] == 0
        assert metadata['lookups_failed'] == 3  # All marked as failed due to queue timeout

    # ========== Concurrency Tests ==========

    def test_max_concurrent_limit(
        self, mock_executor, mock_merger, sample_input_data
    ):
        """Test that max concurrent executions limit is respected."""
        # Create orchestrator with low concurrency limit
        config = {'max_concurrent_executions': 2}
        orchestrator = LookUpOrchestrator(mock_executor, mock_merger, config)

        # Create many projects
        projects = []
        for i in range(10):
            project = MagicMock()
            project.id = uuid.uuid4()
            project.name = f"Look-Up {i+1}"
            projects.append(project)

        # Add small delay to executor to simulate work
        def slow_execute(project, input_data):
            time.sleep(0.01)  # Small delay
            return {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {'field': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 10
            }

        mock_executor.execute.side_effect = slow_execute

        # Execute
        result = orchestrator.execute_lookups(sample_input_data, projects)

        # Should complete successfully despite concurrency limit
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 10
        assert metadata['lookups_successful'] == 10

    # ========== Result Merging Tests ==========

    def test_successful_merge(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor, mock_merger
    ):
        """Test that successful enrichments are properly merged."""
        # Setup merger to return specific merged data
        mock_merger.merge.return_value = {
            'data': {
                'vendor': 'Slack',
                'category': 'SaaS',
                'type': 'Communication'
            },
            'conflicts_resolved': 2,
            'enrichment_details': [
                {'lookup_project_name': 'Look-Up 1', 'fields_added': ['vendor']},
                {'lookup_project_name': 'Look-Up 2', 'fields_added': ['category']},
                {'lookup_project_name': 'Look-Up 3', 'fields_added': ['type']}
            ]
        }

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Check merged enrichment
        assert result['lookup_enrichment'] == {
            'vendor': 'Slack',
            'category': 'SaaS',
            'type': 'Communication'
        }

        # Check metadata
        metadata = result['_lookup_metadata']
        assert metadata['conflicts_resolved'] == 2

    # ========== Error Recovery Tests ==========

    def test_executor_exception_handling(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor
    ):
        """Test handling of unexpected exceptions from executor."""
        # Make executor raise exception for one project
        def execute_with_exception(project, input_data):
            if project.name == "Look-Up 2":
                raise ValueError("Unexpected error in executor")
            return {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {'field': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 100
            }

        mock_executor.execute.side_effect = execute_with_exception

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Should handle exception gracefully
        metadata = result['_lookup_metadata']
        assert metadata['lookups_executed'] == 3
        assert metadata['lookups_successful'] == 2
        assert metadata['lookups_failed'] == 1

        # Check that error is captured
        failed_enrichment = next(
            e for e in metadata['enrichments']
            if e['status'] == 'failed' and 'Unexpected error' in e['error']
        )
        assert failed_enrichment is not None

    # ========== Metadata Tests ==========

    def test_execution_metadata(
        self, orchestrator, sample_input_data, mock_projects
    ):
        """Test that execution metadata is properly populated."""
        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        metadata = result['_lookup_metadata']

        # Check all required metadata fields
        assert 'execution_id' in metadata
        assert isinstance(metadata['execution_id'], str)
        assert len(metadata['execution_id']) == 36  # UUID format

        assert 'executed_at' in metadata
        assert 'T' in metadata['executed_at']  # ISO8601 format

        assert 'total_execution_time_ms' in metadata
        assert metadata['total_execution_time_ms'] >= 0

        assert 'enrichments' in metadata
        assert len(metadata['enrichments']) >= metadata['lookups_successful']

    def test_enrichments_list_includes_all_results(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor
    ):
        """Test that enrichments list includes both successful and failed results."""
        # Setup mixed results
        def execute_side_effect(project, input_data):
            if project.name == "Look-Up 2":
                return {
                    'status': 'failed',
                    'project_id': project.id,
                    'project_name': project.name,
                    'error': 'Test failure',
                    'execution_time_ms': 50,
                    'cached': False
                }
            return {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {'field': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 100
            }

        mock_executor.execute.side_effect = execute_side_effect

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        metadata = result['_lookup_metadata']
        enrichments = metadata['enrichments']

        # Should have all 3 enrichments (2 success + 1 failed)
        assert len(enrichments) == 3

        # Check statuses
        statuses = [e['status'] for e in enrichments]
        assert statuses.count('success') == 2
        assert statuses.count('failed') == 1

    # ========== Configuration Tests ==========

    def test_default_configuration(self, mock_executor, mock_merger):
        """Test orchestrator with default configuration."""
        orchestrator = LookUpOrchestrator(mock_executor, mock_merger)

        assert orchestrator.max_concurrent == 10
        assert orchestrator.queue_timeout == 120
        assert orchestrator.execution_timeout == 30

    def test_custom_configuration(self, mock_executor, mock_merger):
        """Test orchestrator with custom configuration."""
        config = {
            'max_concurrent_executions': 20,
            'queue_timeout_seconds': 300,
            'execution_timeout_seconds': 60
        }

        orchestrator = LookUpOrchestrator(mock_executor, mock_merger, config)

        assert orchestrator.max_concurrent == 20
        assert orchestrator.queue_timeout == 300
        assert orchestrator.execution_timeout == 60

    # ========== Integration Tests ==========

    @patch('lookup.services.lookup_orchestrator.logger')
    def test_logging(
        self, mock_logger, orchestrator, sample_input_data,
        mock_projects
    ):
        """Test that appropriate logging is performed."""
        orchestrator.execute_lookups(sample_input_data, mock_projects)

        # Should log start and completion
        assert mock_logger.info.call_count >= 2
        start_log = mock_logger.info.call_args_list[0][0][0]
        assert 'Starting orchestrated execution' in start_log

        completion_log = mock_logger.info.call_args_list[-1][0][0]
        assert 'completed' in completion_log

    def test_execution_id_propagation(
        self, orchestrator, sample_input_data, mock_projects,
        mock_executor
    ):
        """Test that execution ID is propagated to individual executions."""
        # Capture execution results
        captured_results = []

        def capture_execute(project, input_data):
            result = {
                'status': 'success',
                'project_id': project.id,
                'project_name': project.name,
                'data': {'field': 'value'},
                'confidence': 0.9,
                'cached': False,
                'execution_time_ms': 100
            }
            captured_results.append(result)
            return result

        mock_executor.execute.side_effect = capture_execute

        result = orchestrator.execute_lookups(sample_input_data, mock_projects)

        execution_id = result['_lookup_metadata']['execution_id']

        # Check that execution_id is added to enrichments
        for enrichment in result['_lookup_metadata']['enrichments']:
            if 'execution_id' in enrichment:
                assert enrichment['execution_id'] == execution_id
