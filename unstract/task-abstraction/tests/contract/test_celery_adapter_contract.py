"""
Celery Backend Adapter Contract Test

This test validates that the Celery backend adapter conforms to the TaskClient interface
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
from unstract.task_abstraction.backends.celery_backend import CeleryTaskClient


@pytest.mark.contract
@pytest.mark.celery
class TestCeleryBackendAdapterContract:
    """Contract tests for Celery backend adapter compliance."""

    @pytest.fixture
    async def celery_client(self) -> CeleryTaskClient:
        """Create a Celery task client for testing."""
        # This will fail initially - CeleryTaskClient doesn't exist yet
        client = CeleryTaskClient(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/0"
        )
        await client.startup()
        yield client
        await client.shutdown()

    @pytest.fixture
    def sample_workflow_definition(self) -> WorkflowDefinition:
        """Sample workflow definition for testing."""
        return WorkflowDefinition(
            config=WorkflowConfig(
                name="test-celery-workflow",
                description="Test workflow for Celery backend",
                timeout_minutes=20
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="preprocess-document",
                        timeout_minutes=5
                    ),
                    function_name="preprocess_document",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="extract-content",
                        timeout_minutes=10
                    ),
                    function_name="extract_content",
                    parents=["preprocess-document"]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="post-process",
                        timeout_minutes=3
                    ),
                    function_name="post_process",
                    parents=["extract-content"]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="generate-summary",
                        timeout_minutes=5
                    ),
                    function_name="generate_summary",
                    parents=["extract-content"]
                )
            ]
        )

    @pytest.mark.asyncio
    async def test_client_lifecycle(self, celery_client: CeleryTaskClient):
        """Test client startup and shutdown lifecycle."""
        # Test that client can start and stop cleanly
        assert celery_client.is_connected
        
        # Test shutdown
        await celery_client.shutdown()
        assert not celery_client.is_connected
        
        # Test restart
        await celery_client.startup()
        assert celery_client.is_connected

    @pytest.mark.asyncio
    async def test_workflow_registration(
        self, 
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow registration capabilities."""
        # This will fail - register_workflow method doesn't exist
        registration_result = await celery_client.register_workflow(
            sample_workflow_definition
        )
        
        assert registration_result.success
        assert registration_result.workflow_id is not None
        assert registration_result.backend_workflow_id is not None

    @pytest.mark.asyncio
    async def test_workflow_execution_async(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test asynchronous workflow execution."""
        # Register workflow first
        await celery_client.register_workflow(sample_workflow_definition)
        
        input_data = {
            "document_path": "/test/complex_document.pdf",
            "processing_options": {
                "extract_tables": True,
                "extract_images": False,
                "language": "en"
            }
        }
        
        # This will fail - run_workflow_async method doesn't exist
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            input_data
        )
        
        assert workflow_id is not None
        assert isinstance(workflow_id, str)

    @pytest.mark.asyncio
    async def test_workflow_result_retrieval(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow result retrieval."""
        # Register and execute workflow
        await celery_client.register_workflow(sample_workflow_definition)
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_result method doesn't exist
        result = await celery_client.get_workflow_result(workflow_id)
        
        assert isinstance(result, WorkflowResult)
        assert result.workflow_id == workflow_id
        assert result.status in ["completed", "failed", "running", "revoked"]

    @pytest.mark.asyncio
    async def test_task_result_retrieval(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test individual task result retrieval."""
        # Execute workflow
        await celery_client.register_workflow(sample_workflow_definition)
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            {"test": "data"}
        )
        
        # Wait for some processing
        await asyncio.sleep(1)
        
        # This will fail - get_task_result method doesn't exist
        task_result = await celery_client.get_task_result(
            workflow_id, 
            "preprocess-document"
        )
        
        assert isinstance(task_result, TaskResult)
        assert task_result.task_name == "preprocess-document"
        assert task_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_workflow_cancellation(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow cancellation capability."""
        await celery_client.register_workflow(sample_workflow_definition)
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            {"test": "data"}
        )
        
        # This will fail - cancel_workflow method doesn't exist
        cancellation_result = await celery_client.cancel_workflow(workflow_id)
        
        assert cancellation_result.success
        assert cancellation_result.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_error_handling_workflow_not_found(
        self,
        celery_client: CeleryTaskClient
    ):
        """Test error handling for non-existent workflow."""
        with pytest.raises(Exception) as exc_info:
            await celery_client.run_workflow_async(
                "non-existent-workflow",
                {"test": "data"}
            )
        
        assert "workflow not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_error_handling_invalid_input(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test error handling for invalid input data."""
        await celery_client.register_workflow(sample_workflow_definition)
        
        # Test with invalid input data type
        with pytest.raises(Exception) as exc_info:
            await celery_client.run_workflow_async(
                "test-celery-workflow",
                []  # Should be dict
            )
        
        assert "invalid input" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """Test handling of connection failures."""
        # Create client with invalid broker URL
        invalid_client = CeleryTaskClient(
            broker_url="redis://invalid:9999/0",
            result_backend="redis://invalid:9999/0"
        )
        
        with pytest.raises(Exception) as exc_info:
            await invalid_client.startup()
        
        assert "connection" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test concurrent workflow execution capability."""
        await celery_client.register_workflow(sample_workflow_definition)
        
        # Launch multiple workflows concurrently
        tasks = []
        for i in range(5):
            task = celery_client.run_workflow_async(
                "test-celery-workflow",
                {"test": f"data_{i}"}
            )
            tasks.append(task)
        
        # Wait for all to start
        workflow_ids = await asyncio.gather(*tasks)
        
        assert len(workflow_ids) == 5
        assert len(set(workflow_ids)) == 5  # All unique IDs

    @pytest.mark.asyncio
    async def test_workflow_status_tracking(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test workflow status tracking through execution."""
        await celery_client.register_workflow(sample_workflow_definition)
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            {"test": "data"}
        )
        
        # This will fail - get_workflow_status method doesn't exist
        status = await celery_client.get_workflow_status(workflow_id)
        
        assert status in ["pending", "started", "success", "failure", "revoked"]

    @pytest.mark.asyncio
    async def test_celery_task_routing(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Celery-specific task routing configuration."""
        # Register workflow with routing configuration
        workflow_with_routing = WorkflowDefinition(
            config=WorkflowConfig(
                name="test-routing-workflow",
                description="Test workflow with task routing",
                timeout_minutes=10
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="cpu-intensive-task",
                        timeout_minutes=5,
                        queue="cpu_queue",
                        routing_key="cpu.tasks"
                    ),
                    function_name="cpu_intensive_task",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(
                        name="io-intensive-task",
                        timeout_minutes=5,
                        queue="io_queue",
                        routing_key="io.tasks"
                    ),
                    function_name="io_intensive_task",
                    parents=[]
                )
            ]
        )
        
        # This will fail - queue/routing_key handling doesn't exist
        registration_result = await celery_client.register_workflow(
            workflow_with_routing
        )
        
        assert registration_result.success

    @pytest.mark.asyncio
    async def test_celery_retry_policy(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Celery-specific retry policy configuration."""
        # Register workflow with retry configuration
        workflow_with_retry = WorkflowDefinition(
            config=WorkflowConfig(
                name="test-retry-workflow",
                description="Test workflow with Celery retry policy",
                timeout_minutes=10
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(
                        name="flaky-celery-task",
                        timeout_minutes=2,
                        retry_policy={
                            "max_retries": 3,
                            "countdown": 60,
                            "retry_backoff": True,
                            "retry_backoff_max": 700,
                            "retry_jitter": False
                        }
                    ),
                    function_name="flaky_celery_task",
                    parents=[]
                )
            ]
        )
        
        # This will fail - Celery retry policy handling doesn't exist
        registration_result = await celery_client.register_workflow(
            workflow_with_retry
        )
        
        assert registration_result.success

    @pytest.mark.asyncio
    async def test_celery_chord_pattern(
        self,
        celery_client: CeleryTaskClient
    ):
        """Test Celery chord pattern for parallel task execution."""
        # Define workflow with parallel tasks and a callback
        parallel_workflow = WorkflowDefinition(
            config=WorkflowConfig(
                name="test-chord-workflow",
                description="Test Celery chord pattern",
                timeout_minutes=15
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(name="parallel-task-1", timeout_minutes=5),
                    function_name="parallel_task",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(name="parallel-task-2", timeout_minutes=5),
                    function_name="parallel_task",
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(name="parallel-task-3", timeout_minutes=5),
                    function_name="parallel_task", 
                    parents=[]
                ),
                TaskDefinition(
                    config=TaskConfig(name="chord-callback", timeout_minutes=3),
                    function_name="chord_callback",
                    parents=["parallel-task-1", "parallel-task-2", "parallel-task-3"]
                )
            ]
        )
        
        # This will fail - chord pattern handling doesn't exist
        await celery_client.register_workflow(parallel_workflow)
        workflow_id = await celery_client.run_workflow_async(
            "test-chord-workflow",
            {"parallel_count": 3}
        )
        
        assert workflow_id is not None

    @pytest.mark.asyncio
    async def test_backend_specific_configuration(
        self,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Celery-specific configuration options."""
        # This will fail - CeleryTaskClient constructor options don't exist
        celery_client = CeleryTaskClient(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/1",
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            result_expires=3600,
            timezone="UTC"
        )
        
        await celery_client.startup()
        
        # Test configuration is applied
        assert celery_client.task_serializer == "json"
        assert celery_client.result_serializer == "json"
        assert celery_client.result_expires == 3600
        
        await celery_client.shutdown()

    @pytest.mark.asyncio
    async def test_celery_task_inspect(
        self,
        celery_client: CeleryTaskClient,
        sample_workflow_definition: WorkflowDefinition
    ):
        """Test Celery task inspection capabilities."""
        await celery_client.register_workflow(sample_workflow_definition)
        workflow_id = await celery_client.run_workflow_async(
            "test-celery-workflow",
            {"test": "data"}
        )
        
        # This will fail - inspect methods don't exist
        active_tasks = await celery_client.get_active_tasks()
        reserved_tasks = await celery_client.get_reserved_tasks()
        
        assert isinstance(active_tasks, list)
        assert isinstance(reserved_tasks, list)

    def test_client_interface_compliance(self):
        """Test that CeleryTaskClient implements TaskClient interface."""
        # This will fail - CeleryTaskClient doesn't exist
        assert issubclass(CeleryTaskClient, TaskClient)
        
        # Check required methods exist
        required_methods = [
            'startup', 'shutdown', 'register_workflow', 'run_workflow_async',
            'get_workflow_result', 'get_task_result', 'cancel_workflow'
        ]
        
        for method_name in required_methods:
            assert hasattr(CeleryTaskClient, method_name)
            assert callable(getattr(CeleryTaskClient, method_name))

    def test_celery_specific_methods(self):
        """Test Celery-specific methods exist."""
        # This will fail - CeleryTaskClient and methods don't exist
        celery_specific_methods = [
            'get_active_tasks', 'get_reserved_tasks', 'purge_queue'
        ]
        
        for method_name in celery_specific_methods:
            assert hasattr(CeleryTaskClient, method_name)
            assert callable(getattr(CeleryTaskClient, method_name))