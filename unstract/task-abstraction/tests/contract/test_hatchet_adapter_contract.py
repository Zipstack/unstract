"""
Hatchet Backend Adapter Contract Test

This test validates that the Hatchet backend adapter conforms to the TaskClient interface
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
from unstract.task_abstraction.backends.hatchet_backend import HatchetTaskClient


@pytest.mark.contract
@pytest.mark.hatchet
class TestHatchetBackendAdapterContract:
    """Contract tests for Hatchet backend adapter compliance."""

    @pytest.fixture
    async def hatchet_client(self) -> HatchetTaskClient:
        """Create a Hatchet task client for testing."""
        # This will fail initially - HatchetTaskClient doesn't exist yet
        client = HatchetTaskClient(
            server_url="http://localhost:8080",
            token="test_token"
        )
        await client.startup()
        yield client
        await client.shutdown()

    @pytest.fixture
    def sample_workflow_definition(self) -> WorkflowDefinition:
        """Sample workflow definition for testing."""
        return WorkflowDefinition(
            config=WorkflowConfig(
                name="test-hatchet-workflow",
                description="Test workflow for Hatchet backend",
                timeout_minutes=10
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="extract-text",
                        timeout_minutes=5
                    ),
                    function_name="extract_text",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="process-llm",
                        timeout_minutes=8
                    ),
                    function_name="process_llm",
                    parents=["extract-text"]
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_client_lifecycle(self, hatchet_client: HatchetTaskClient):
        """Test client startup and shutdown lifecycle."""
        # Test that client can start and stop cleanly
        assert hatchet_client.is_connected
        
        # Test shutdown
        await hatchet_client.shutdown()
        assert not hatchet_client.is_connected
        
        # Test restart
        await hatchet_client.startup()
        assert hatchet_client.is_connected

    @pytest.mark.asyncio
    async def test_workflow_registration(
        self, 
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow registration capabilities."""
        # This will fail - register_workflow method doesn't exist
        registration_result = await hatchet_client.register_workflow(
            sample_workflow_definition
        )
        
        assert registration_result.success
        assert registration_result.workflow_id is not None
        assert registration_result.backend_workflow_id is not None

    @pytest.mark.asyncio
    async def test_workflow_execution_async(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test asynchronous workflow execution."""
        # Register workflow first
        await hatchet_client.register_workflow(sample_workflow_definition)
        
        input_data = {
            "document_path": "/test/sample.pdf",
            "output_configs": [{"name": "summary", "prompt": "Summarize this"}]
        }
        
        # This will fail - run_workflow_async method doesn't exist
        workflow_id = await hatchet_client.run_workflow_async(
            "test-hatchet-workflow",
            input_data
        )
        
        assert workflow_id is not None
        assert isinstance(workflow_id, str)

    @pytest.mark.asyncio
    async def test_workflow_result_retrieval(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow result retrieval."""
        # Register and execute workflow
        await hatchet_client.register_workflow(sample_workflow_definition)
        workflow_id = await hatchet_client.run_workflow_async(
            "test-hatchet-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_result method doesn't exist
        result = await hatchet_client.get_workflow_result(workflow_id)
        
        assert isinstance(result, WorkflowResult)
        assert result.workflow_id == workflow_id
        assert result.status in ["completed", "failed", "running"]

    @pytest.mark.asyncio
    async def test_task_result_retrieval(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test individual task result retrieval."""
        # Execute workflow
        await hatchet_client.register_workflow(sample_workflow_definition)
        workflow_id = await hatchet_client.run_workflow_async(
            "test-hatchet-workflow",
            {"test": "data"}
        )
        
        # Wait for completion (in real test, would poll)
        await asyncio.sleep(1)
        
        # This will fail - get_task_result method doesn't exist
        task_result = await hatchet_client.get_task_result(
            workflow_id, 
            "extract-text"
        )
        
        assert isinstance(task_result, TaskResult)
        assert task_result.task_name == "extract-text"
        assert task_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_workflow_cancellation(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow cancellation capability."""
        await hatchet_client.register_workflow(sample_workflow_definition)
        workflow_id = await hatchet_client.run_workflow_async(
            "test-hatchet-workflow",
            {"test": "data"}
        )
        
        # This will fail - cancel_workflow method doesn't exist
        cancellation_result = await hatchet_client.cancel_workflow(workflow_id)
        
        assert cancellation_result.success
        assert cancellation_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_error_handling_workflow_not_found(
        self,
        hatchet_client: HatchetTaskClient
    ):
        """Test error handling for non-existent workflow."""
        with pytest.raises(Exception) as exc_info:
            await hatchet_client.run_workflow_async(
                "non-existent-workflow",
                {"test": "data"}
            )
        
        assert "workflow not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test error handling for invalid input data."""
        await hatchet_client.register_workflow(sample_workflow_definition)
        
        # Test with invalid input data type
        with pytest.raises(Exception) as exc_info:
            await hatchet_client.run_workflow_async(
                "test-hatchet-workflow",
                "invalid_input_type"  # Should be dict
            )
        
        assert "invalid input" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """Test handling of connection failures."""
        # Create client with invalid server URL
        invalid_client = HatchetTaskClient(
            server_url="http://invalid:9999",
            token="test_token"
        )
        
        with pytest.raises(Exception) as exc_info:
            await invalid_client.startup()
        
        assert "connection" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(
        self,
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test concurrent workflow execution capability."""
        await hatchet_client.register_workflow(sample_workflow_definition)
        
        # Launch multiple workflows concurrently
        tasks = []
        for i in range(3):
            task = hatchet_client.run_workflow_async(
                "test-hatchet-workflow",
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
        hatchet_client: HatchetTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow status tracking through execution."""
        await hatchet_client.register_workflow(sample_workflow_definition)
        workflow_id = await hatchet_client.run_workflow_async(
            "test-hatchet-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_status method doesn't exist
        status = await hatchet_client.get_workflow_status(workflow_id)
        
        assert status in ["pending", "running", "completed", "failed", "cancelled"]

    @pytest.mark.asyncio
    async def test_backend_specific_configuration(
        self,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Hatchet-specific configuration options."""
        # This will fail - HatchetTaskClient constructor options don't exist
        hatchet_client = HatchetTaskClient(
            server_url="http://localhost:8080",
            token="test_token",
            namespace="test_namespace",
            worker_name="test_worker",
            max_runs=5
        )
        
        await hatchet_client.startup()
        
        # Test configuration is applied
        assert hatchet_client.namespace == "test_namespace"
        assert hatchet_client.worker_name == "test_worker"
        assert hatchet_client.max_runs == 5
        
        await hatchet_client.shutdown()

    def test_client_interface_compliance(self):
        """Test that HatchetTaskClient implements TaskClient interface."""
        # This will fail - HatchetTaskClient doesn't exist
        assert issubclass(HatchetTaskClient, TaskClient)
        
        # Check required methods exist
        required_methods = [
            'startup', 'shutdown', 'register_workflow', 'run_workflow_async',
            'get_workflow_result', 'get_task_result', 'cancel_workflow'
        ]
        
        for method_name in required_methods:
            assert hasattr(HatchetTaskClient, method_name)
            assert callable(getattr(HatchetTaskClient, method_name))