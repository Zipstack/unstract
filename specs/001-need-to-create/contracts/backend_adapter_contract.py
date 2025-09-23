"""
Backend Adapter Contract Tests

These contract tests ensure all backend implementations conform to the unified TaskClient interface.
Each backend adapter must pass these tests to ensure compatibility with the task abstraction layer.
"""

import pytest
import asyncio
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from unstract.task_abstraction.base.client import TaskClient
from unstract.task_abstraction.models import (
    WorkflowDefinition, TaskDefinition, WorkflowResult, WorkflowStatus,
    WorkflowOptions, TaskConfig, WorkflowConfig, Priority, TaskRetryConfig
)


class BackendAdapterContractTest(ABC):
    """
    Abstract base class for backend adapter contract tests.
    Each backend implementation must implement these tests.
    """
    
    @abstractmethod
    def create_client(self) -> TaskClient:
        """Create a client instance for testing."""
        pass
    
    @abstractmethod
    def get_test_workflow_definition(self) -> WorkflowDefinition:
        """Return a simple workflow definition for testing."""
        pass
    
    @pytest.mark.asyncio
    async def test_client_lifecycle(self):
        """Test basic client startup and shutdown."""
        client = self.create_client()
        
        # Client should not be started initially
        assert not client.is_started
        
        # Startup should succeed
        await client.startup()
        assert client.is_started
        
        # Shutdown should succeed
        await client.shutdown()
        assert not client.is_started
    
    @pytest.mark.asyncio
    async def test_workflow_registration(self):
        """Test workflow registration functionality."""
        client = self.create_client()
        await client.startup()
        
        try:
            workflow_def = self.get_test_workflow_definition()
            
            # Registration should succeed
            await client.register_workflow(workflow_def)
            
            # Should be able to retrieve registered workflow
            registered_workflows = client.list_workflows()
            assert workflow_def.config.name in registered_workflows
            
        finally:
            await client.shutdown()
    
    @pytest.mark.asyncio
    async def test_workflow_execution(self):
        """Test basic workflow execution."""
        client = self.create_client()
        await client.startup()
        
        try:
            # Register test workflow
            workflow_def = self.get_test_workflow_definition()
            await client.register_workflow(workflow_def)
            
            # Execute workflow
            input_data = {"test_input": "value"}
            workflow_id = await client.run_workflow_async(
                workflow_def.config.name, 
                input_data
            )
            
            # Should return valid workflow ID
            assert isinstance(workflow_id, str)
            assert len(workflow_id) > 0
            
            # Should be able to get result
            result = await client.get_workflow_result(workflow_id)
            assert isinstance(result, WorkflowResult)
            assert result.workflow_id == workflow_id
            
        finally:
            await client.shutdown()
    
    @pytest.mark.asyncio
    async def test_workflow_failure_handling(self):
        """Test workflow failure handling."""
        client = self.create_client()
        await client.startup()
        
        try:
            # Create a workflow that will fail
            failing_workflow = self.get_failing_workflow_definition()
            await client.register_workflow(failing_workflow)
            
            # Execute failing workflow
            workflow_id = await client.run_workflow_async(
                failing_workflow.config.name,
                {"test_input": "value"}
            )
            
            # Wait for completion and check failure status
            result = await self._wait_for_completion(client, workflow_id)
            assert result.status == WorkflowStatus.FAILED
            assert result.error is not None
            
        finally:
            await client.shutdown()
    
    @pytest.mark.asyncio
    async def test_workflow_retry_behavior(self):
        """Test workflow retry behavior."""
        client = self.create_client()
        await client.startup()
        
        try:
            # Create workflow with retry configuration
            retry_workflow = self.get_retry_workflow_definition()
            await client.register_workflow(retry_workflow)
            
            # Execute workflow
            workflow_id = await client.run_workflow_async(
                retry_workflow.config.name,
                {"test_input": "value"}
            )
            
            # Monitor retry attempts
            result = await self._wait_for_completion(client, workflow_id)
            
            # Verify retry behavior (implementation specific)
            # At minimum, should track attempt count
            assert hasattr(result, 'attempt_count') or len(result.task_results) > 0
            
        finally:
            await client.shutdown()
    
    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(self):
        """Test concurrent workflow execution."""
        client = self.create_client()
        await client.startup()
        
        try:
            workflow_def = self.get_test_workflow_definition()
            await client.register_workflow(workflow_def)
            
            # Start multiple workflows concurrently
            workflow_count = 3
            workflow_ids = []
            
            for i in range(workflow_count):
                workflow_id = await client.run_workflow_async(
                    workflow_def.config.name,
                    {"test_input": f"value_{i}"}
                )
                workflow_ids.append(workflow_id)
            
            # Wait for all to complete
            results = await asyncio.gather(*[
                self._wait_for_completion(client, workflow_id)
                for workflow_id in workflow_ids
            ])
            
            # All should complete successfully
            assert len(results) == workflow_count
            for result in results:
                assert result.status == WorkflowStatus.COMPLETED
                
        finally:
            await client.shutdown()
    
    @pytest.mark.asyncio
    async def test_workflow_timeout_handling(self):
        """Test workflow timeout handling."""
        client = self.create_client()
        await client.startup()
        
        try:
            # Create workflow with short timeout
            timeout_workflow = self.get_timeout_workflow_definition()
            await client.register_workflow(timeout_workflow)
            
            # Execute workflow
            workflow_id = await client.run_workflow_async(
                timeout_workflow.config.name,
                {"test_input": "value"}
            )
            
            # Should timeout and fail
            result = await self._wait_for_completion(client, workflow_id)
            assert result.status in [WorkflowStatus.FAILED, WorkflowStatus.TIMEOUT]
            
        finally:
            await client.shutdown()
    
    async def _wait_for_completion(
        self, 
        client: TaskClient, 
        workflow_id: str, 
        timeout: int = 30
    ) -> WorkflowResult:
        """Wait for workflow to complete with timeout."""
        for _ in range(timeout):
            result = await client.get_workflow_result(workflow_id)
            if result.is_completed:
                return result
            await asyncio.sleep(1)
        
        raise TimeoutError(f"Workflow {workflow_id} did not complete within {timeout}s")
    
    def get_failing_workflow_definition(self) -> WorkflowDefinition:
        """Return a workflow definition that will fail."""
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="failing_task",
            retry_config=TaskRetryConfig(max_retries=1),
            timeout=timedelta(seconds=10)
        )
        
        task_def = TaskDefinition(
            name="failing_task",
            function_name="failing_function",
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="failing_workflow",
            version="1.0.0",
            description="Test workflow that fails"
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )
    
    def get_retry_workflow_definition(self) -> WorkflowDefinition:
        """Return a workflow definition with retry behavior."""
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="retry_task",
            retry_config=TaskRetryConfig(max_retries=3),
            timeout=timedelta(seconds=30)
        )
        
        task_def = TaskDefinition(
            name="retry_task", 
            function_name="retry_function",
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="retry_workflow",
            version="1.0.0",
            description="Test workflow with retries"
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )
    
    def get_timeout_workflow_definition(self) -> WorkflowDefinition:
        """Return a workflow definition that will timeout."""
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="timeout_task",
            timeout=timedelta(seconds=1),  # Very short timeout
            retry_config=TaskRetryConfig(max_retries=0)
        )
        
        task_def = TaskDefinition(
            name="timeout_task",
            function_name="slow_function", 
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="timeout_workflow",
            version="1.0.0",
            description="Test workflow that times out",
            timeout=timedelta(seconds=2)
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )


# Concrete contract tests for each backend
class HatchetAdapterContractTest(BackendAdapterContractTest):
    """Contract tests for Hatchet backend adapter."""
    
    def create_client(self) -> TaskClient:
        from unstract.task_abstraction import get_task_client
        return get_task_client(backend_override="hatchet")
    
    def get_test_workflow_definition(self) -> WorkflowDefinition:
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="test_task",
            timeout=timedelta(minutes=5),
            retry_config=TaskRetryConfig(max_retries=2),
            priority=Priority.NORMAL
        )
        
        task_def = TaskDefinition(
            name="test_task",
            function_name="test_function",
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="hatchet_test_workflow",
            version="1.0.0",
            description="Test workflow for Hatchet backend"
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )


class TemporalAdapterContractTest(BackendAdapterContractTest):
    """Contract tests for Temporal backend adapter."""
    
    def create_client(self) -> TaskClient:
        from unstract.task_abstraction import get_task_client
        return get_task_client(backend_override="temporal")
    
    def get_test_workflow_definition(self) -> WorkflowDefinition:
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="test_task",
            timeout=timedelta(minutes=5),
            retry_config=TaskRetryConfig(max_retries=2),
            priority=Priority.NORMAL
        )
        
        task_def = TaskDefinition(
            name="test_task", 
            function_name="test_function",
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="temporal_test_workflow",
            version="1.0.0", 
            description="Test workflow for Temporal backend"
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )


class CeleryAdapterContractTest(BackendAdapterContractTest):
    """Contract tests for Celery backend adapter."""
    
    def create_client(self) -> TaskClient:
        from unstract.task_abstraction import get_task_client
        return get_task_client(backend_override="celery")
    
    def get_test_workflow_definition(self) -> WorkflowDefinition:
        from datetime import timedelta
        
        task_config = TaskConfig(
            name="test_task",
            timeout=timedelta(minutes=5),
            retry_config=TaskRetryConfig(max_retries=2),
            priority=Priority.NORMAL
        )
        
        task_def = TaskDefinition(
            name="test_task",
            function_name="test_function", 
            config=task_config
        )
        
        workflow_config = WorkflowConfig(
            name="celery_test_workflow",
            version="1.0.0",
            description="Test workflow for Celery backend"
        )
        
        return WorkflowDefinition(
            config=workflow_config,
            tasks=[task_def]
        )


# Test runner for all backends
def run_all_backend_contract_tests():
    """Run contract tests for all backend implementations."""
    backends = [
        ("hatchet", HatchetAdapterContractTest()),
        ("temporal", TemporalAdapterContractTest()),
        ("celery", CeleryAdapterContractTest())
    ]
    
    results = {}
    
    for backend_name, test_class in backends:
        print(f"\nRunning contract tests for {backend_name} backend...")
        try:
            # Run all test methods
            test_methods = [
                method for method in dir(test_class)
                if method.startswith('test_') and callable(getattr(test_class, method))
            ]
            
            backend_results = {}
            for method_name in test_methods:
                try:
                    method = getattr(test_class, method_name)
                    asyncio.run(method())
                    backend_results[method_name] = "PASS"
                    print(f"  ✓ {method_name}")
                except Exception as e:
                    backend_results[method_name] = f"FAIL: {e}"
                    print(f"  ✗ {method_name}: {e}")
            
            results[backend_name] = backend_results
            
        except Exception as e:
            results[backend_name] = {"error": f"Backend initialization failed: {e}"}
            print(f"  ✗ Backend {backend_name} failed to initialize: {e}")
    
    return results


if __name__ == "__main__":
    results = run_all_backend_contract_tests()
    
    # Summary report
    print("\n" + "="*60)
    print("BACKEND CONTRACT TEST SUMMARY")
    print("="*60)
    
    for backend, tests in results.items():
        print(f"\n{backend.upper()} Backend:")
        if "error" in tests:
            print(f"  Error: {tests['error']}")
        else:
            passed = sum(1 for result in tests.values() if result == "PASS")
            total = len(tests)
            print(f"  Tests: {passed}/{total} passed")
            
            if passed < total:
                for test, result in tests.items():
                    if result != "PASS":
                        print(f"    ✗ {test}: {result}")