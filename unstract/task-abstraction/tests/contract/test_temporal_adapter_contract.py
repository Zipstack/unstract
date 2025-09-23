"""
Temporal Backend Adapter Contract Test

This test validates that the Temporal backend adapter conforms to the TaskClient interface
and the backend adapter contract. These tests MUST FAIL initially (TDD approach).
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, Mock, patch

from unstract.task_abstraction.interfaces import TaskClient, TaskResult, WorkflowResult
from unstract.task_abstraction.models import (
    WorkflowDefinition, TaskDefinition, WorkflowConfig, TaskConfig
)
from unstract.task_abstraction.backends.temporal_backend import TemporalTaskClient


@pytest.mark.contract
@pytest.mark.temporal
class TestTemporalBackendAdapterContract:
    """Contract tests for Temporal backend adapter compliance."""

    @pytest.fixture
    async def temporal_client(self) -> TemporalTaskClient:
        """Create a Temporal task client for testing."""
        # This will fail initially - TemporalTaskClient doesn't exist yet
        client = TemporalTaskClient(
            host_port="localhost:7233",
            namespace="test-namespace"
        )
        await client.startup()
        yield client
        await client.shutdown()

    @pytest.fixture
    def sample_workflow_definition(self) -> WorkflowDefinition:
        """Sample workflow definition for testing."""
        return WorkflowDefinition(
            config=WorkflowConfig(
                name="test-temporal-workflow",
                description="Test workflow for Temporal backend",
                timeout_minutes=15
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="extract-data",
                        timeout_minutes=5
                    ),
                    function_name="extract_data",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="transform-data",
                        timeout_minutes=7
                    ),
                    function_name="transform_data",
                    parents=["extract-data"]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="load-data",
                        timeout_minutes=3
                    ),
                    function_name="load_data",
                    parents=["transform-data"]
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_client_lifecycle(self, temporal_client: TemporalTaskClient):
        """Test client startup and shutdown lifecycle."""
        # Test that client can start and stop cleanly
        assert temporal_client.is_connected
        
        # Test shutdown
        await temporal_client.shutdown()
        assert not temporal_client.is_connected
        
        # Test restart
        await temporal_client.startup()
        assert temporal_client.is_connected

    @pytest.mark.asyncio
    async def test_workflow_registration(
        self, 
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow registration capabilities."""
        # This will fail - register_workflow method doesn't exist
        registration_result = await temporal_client.register_workflow(
            sample_workflow_definition
        )
        
        assert registration_result.success
        assert registration_result.workflow_id is not None
        assert registration_result.backend_workflow_id is not None

    @pytest.mark.asyncio
    async def test_workflow_execution_async(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test asynchronous workflow execution."""
        # Register workflow first
        await temporal_client.register_workflow(sample_workflow_definition)
        
        input_data = {
            "source_path": "/test/input.csv",
            "destination": "postgresql://test",
            "transformation_rules": {"clean": True, "validate": True}
        }
        
        # This will fail - run_workflow_async method doesn't exist
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            input_data
        )
        
        assert workflow_id is not None
        assert isinstance(workflow_id, str)

    @pytest.mark.asyncio
    async def test_workflow_result_retrieval(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow result retrieval."""
        # Register and execute workflow
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_result method doesn't exist
        result = await temporal_client.get_workflow_result(workflow_id)
        
        assert isinstance(result, WorkflowResult)
        assert result.workflow_id == workflow_id
        assert result.status in ["completed", "failed", "running", "terminated"]

    @pytest.mark.asyncio
    async def test_task_result_retrieval(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test individual task result retrieval."""
        # Execute workflow
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # Wait for some processing (in real test, would use proper polling)
        await asyncio.sleep(1)
        
        # This will fail - get_task_result method doesn't exist
        task_result = await temporal_client.get_task_result(
            workflow_id, 
            "extract-data"
        )
        
        assert isinstance(task_result, TaskResult)
        assert task_result.task_name == "extract-data"
        assert task_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_workflow_cancellation(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow cancellation capability."""
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - cancel_workflow method doesn't exist
        cancellation_result = await temporal_client.cancel_workflow(workflow_id)
        
        assert cancellation_result.success
        assert cancellation_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_error_handling_workflow_not_found(
        self,
        temporal_client: TemporalTaskClient
    ):
        """Test error handling for non-existent workflow."""
        with pytest.raises(Exception) as exc_info:
            await temporal_client.run_workflow_async(
                "non-existent-workflow",
                {"test": "data"}
            )
        
        assert "workflow not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test error handling for invalid input data."""
        await temporal_client.register_workflow(sample_workflow_definition)
        
        # Test with invalid input data type
        with pytest.raises(Exception) as exc_info:
            await temporal_client.run_workflow_async(
                "test-temporal-workflow",
                None  # Should be dict
            )
        
        assert "invalid input" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """Test handling of connection failures."""
        # Create client with invalid server
        invalid_client = TemporalTaskClient(
            host_port="invalid:9999",
            namespace="test-namespace"
        )
        
        with pytest.raises(Exception) as exc_info:
            await invalid_client.startup()
        
        assert "connection" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test concurrent workflow execution capability."""
        await temporal_client.register_workflow(sample_workflow_definition)
        
        # Launch multiple workflows concurrently
        tasks = []
        for i in range(3):
            task = temporal_client.run_workflow_async(
                "test-temporal-workflow",
                {"test": f"data_{i}"}
            )
            tasks.append(task)
        
        # Wait for all to start
        workflow_ids = await asyncio.gather(*tasks)
        
        assert len(workflow_ids) == 3
        assert len(set(workflow_ids)) == 3  # All unique IDs

    @pytest.mark.asyncio
    async def test_workflow_status_tracking(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow status tracking through execution."""
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_status method doesn't exist
        status = await temporal_client.get_workflow_status(workflow_id)
        
        assert status in ["running", "completed", "failed", "cancelled", "terminated"]

    @pytest.mark.asyncio
    async def test_temporal_activity_retry_policy(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Temporal-specific retry policy configuration."""
        # Register workflow with retry policy
        workflow_with_retry = WorkflowDefinition(
            config=WorkflowConfig(
                name="test-retry-workflow",
                description="Test workflow with retry policy",
                timeout_minutes=10
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="flaky-task",
                        timeout_minutes=2,
                        retry_policy={
                            "maximum_attempts": 3,
                            "initial_interval_seconds": 1,
                            "maximum_interval_seconds": 10
                        }
                    ),
                    function_name="flaky_task",
                    parents=[]
                )
            ]
        )
        
        # This will fail - retry policy handling doesn't exist
        registration_result = await temporal_client.register_workflow(
            workflow_with_retry
        )
        
        assert registration_result.success

    @pytest.mark.asyncio
    async def test_temporal_signal_handling(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Temporal signal handling capability."""
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - send_signal method doesn't exist
        signal_result = await temporal_client.send_signal(
            workflow_id,
            "pause_signal",
            {"reason": "maintenance"}
        )
        
        assert signal_result.success

    @pytest.mark.asyncio
    async def test_temporal_query_handling(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Temporal query handling capability."""
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - query_workflow method doesn't exist
        query_result = await temporal_client.query_workflow(
            workflow_id,
            "get_progress"
        )
        
        assert query_result is not None

    @pytest.mark.asyncio
    async def test_backend_specific_configuration(
        self,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Temporal-specific configuration options."""
        # This will fail - TemporalTaskClient constructor options don't exist
        temporal_client = TemporalTaskClient(
            host_port="localhost:7233",
            namespace="test-namespace",
            task_queue="test-task-queue",
            identity="test-worker",
            data_converter="json"
        )
        
        await temporal_client.startup()
        
        # Test configuration is applied
        assert temporal_client.namespace == "test-namespace"
        assert temporal_client.task_queue == "test-task-queue"
        assert temporal_client.identity == "test-worker"
        
        await temporal_client.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_history_retrieval(
        self,
        temporal_client: TemporalTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow history retrieval capability."""
        await temporal_client.register_workflow(sample_workflow_definition)
        workflow_id = await temporal_client.run_workflow_async(
            "test-temporal-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_history method doesn't exist
        history = await temporal_client.get_workflow_history(workflow_id)
        
        assert history is not None
        assert len(history.events) > 0

    def test_client_interface_compliance(self):
        """Test that TemporalTaskClient implements TaskClient interface."""
        # This will fail - TemporalTaskClient doesn't exist
        assert issubclass(TemporalTaskClient, TaskClient)
        
        # Check required methods exist
        required_methods = [
            'startup', 'shutdown', 'register_workflow', 'run_workflow_async',
            'get_workflow_result', 'get_task_result', 'cancel_workflow'
        ]
        
        for method_name in required_methods:
            assert hasattr(TemporalTaskClient, method_name)
            assert callable(getattr(TemporalTaskClient, method_name))

    def test_temporal_specific_methods(self):
        """Test Temporal-specific methods exist."""
        # This will fail - TemporalTaskClient and methods don't exist
        temporal_specific_methods = [
            'send_signal', 'query_workflow', 'get_workflow_history'
        ]
        
        for method_name in temporal_specific_methods:
            assert hasattr(TemporalTaskClient, method_name)
            assert callable(getattr(TemporalTaskClient, method_name))