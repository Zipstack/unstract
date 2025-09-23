"""
Circuit Breaker Functionality Integration Test (T010)

This test validates circuit breaker functionality for failure protection and recovery
during backend migrations. These tests MUST FAIL initially (TDD approach).
"""

import pytest
import asyncio
from typing import Dict, Any, List, Callable
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass
from enum import Enum
import time

from unstract.task_abstraction.interfaces import TaskClient


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerTestCase:
    """Test case for circuit breaker scenarios."""
    name: str
    failure_threshold: int
    recovery_timeout: float
    success_threshold: int
    failure_sequence: List[bool]  # True = success, False = failure
    expected_state_transitions: List[CircuitState]


@pytest.mark.integration
@pytest.mark.circuit_breaker
class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker functionality."""

    @pytest.fixture
    def circuit_breaker_test_cases(self) -> List[CircuitBreakerTestCase]:
        """Test cases for circuit breaker scenarios."""
        return [
            CircuitBreakerTestCase(
                name="basic_failure_threshold",
                failure_threshold=3,
                recovery_timeout=1.0,
                success_threshold=2,
                failure_sequence=[False, False, False],  # 3 failures
                expected_state_transitions=[
                    CircuitState.CLOSED,
                    CircuitState.CLOSED, 
                    CircuitState.OPEN
                ]
            ),
            CircuitBreakerTestCase(
                name="recovery_after_timeout",
                failure_threshold=2,
                recovery_timeout=0.5,
                success_threshold=1,
                failure_sequence=[False, False, True],  # 2 failures, then success after timeout
                expected_state_transitions=[
                    CircuitState.CLOSED,
                    CircuitState.OPEN,
                    CircuitState.CLOSED  # Recovered after success
                ]
            ),
            CircuitBreakerTestCase(
                name="half_open_success",
                failure_threshold=2,
                recovery_timeout=0.5,
                success_threshold=2,
                failure_sequence=[False, False, True, True],  # Failures, then successes
                expected_state_transitions=[
                    CircuitState.CLOSED,
                    CircuitState.OPEN,
                    CircuitState.HALF_OPEN,
                    CircuitState.CLOSED
                ]
            ),
            CircuitBreakerTestCase(
                name="half_open_failure",
                failure_threshold=2,
                recovery_timeout=0.5,
                success_threshold=2,
                failure_sequence=[False, False, False],  # Failures, then more failure in half-open
                expected_state_transitions=[
                    CircuitState.CLOSED,
                    CircuitState.OPEN,
                    CircuitState.OPEN  # Back to open after failure in half-open
                ]
            ),
            CircuitBreakerTestCase(
                name="mixed_success_failure",
                failure_threshold=3,
                recovery_timeout=0.5,
                success_threshold=1,
                failure_sequence=[True, False, True, False, False, False],  # Mixed pattern
                expected_state_transitions=[
                    CircuitState.CLOSED,
                    CircuitState.CLOSED,
                    CircuitState.CLOSED,
                    CircuitState.CLOSED,
                    CircuitState.CLOSED,
                    CircuitState.OPEN
                ]
            )
        ]

    @pytest.fixture
    async def circuit_breaker(self):
        """Create circuit breaker for testing."""
        # This will fail initially - CircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import CircuitBreaker
        return CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=1.0,
            success_threshold=2
        )

    @pytest.fixture
    async def migration_circuit_breaker(self):
        """Create migration-specific circuit breaker for testing."""
        # This will fail initially - MigrationCircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import MigrationCircuitBreaker
        return MigrationCircuitBreaker(
            failure_threshold=3,
            recovery_timeout=1.0,
            success_threshold=2
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_transitions(
        self,
        circuit_breaker_test_cases: List[CircuitBreakerTestCase]
    ):
        """Test circuit breaker state transitions under different failure patterns."""
        
        for test_case in circuit_breaker_test_cases:
            # This will fail initially - CircuitBreaker doesn't exist
            from unstract.task_abstraction.circuit_breaker import CircuitBreaker
            
            cb = CircuitBreaker(
                failure_threshold=test_case.failure_threshold,
                recovery_timeout=test_case.recovery_timeout,
                success_threshold=test_case.success_threshold
            )
            
            state_history = [cb.state]  # Initial state should be CLOSED
            
            for i, should_succeed in enumerate(test_case.failure_sequence):
                async def mock_operation():
                    if should_succeed:
                        return {"status": "success", "result": "data"}
                    else:
                        raise Exception(f"Simulated failure #{i}")
                
                # This will fail - call method doesn't exist
                try:
                    result = await cb.call(mock_operation)
                except Exception:
                    pass  # Expected for some failures
                
                # Add small delay for recovery timeout tests
                if i < len(test_case.failure_sequence) - 1:
                    await asyncio.sleep(test_case.recovery_timeout + 0.1)
                
                state_history.append(cb.state)
            
            # Verify state transitions match expected pattern
            expected_transitions = [CircuitState.CLOSED] + test_case.expected_state_transitions
            assert len(state_history) == len(expected_transitions), \
                f"Test case '{test_case.name}': expected {len(expected_transitions)} states, got {len(state_history)}"
            
            for i, (expected, actual) in enumerate(zip(expected_transitions, state_history)):
                assert actual == expected, \
                    f"Test case '{test_case.name}' step {i}: expected {expected}, got {actual}"

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_threshold(self, circuit_breaker):
        """Test circuit breaker opens after failure threshold is reached."""
        
        failure_count = 0
        
        async def failing_operation():
            nonlocal failure_count
            failure_count += 1
            raise Exception(f"Failure #{failure_count}")
        
        async def fallback_operation():
            return {"status": "success", "result": "fallback"}
        
        # Initial state should be closed
        assert circuit_breaker.state == CircuitState.CLOSED
        
        # Execute operations until circuit opens
        for i in range(5):
            result = await circuit_breaker.call(failing_operation, fallback_operation)
            
            if i < circuit_breaker.failure_threshold:
                # Should still attempt primary operation
                assert result["result"] == "fallback"  # Fallback was called
            else:
                # Circuit should be open, only fallback called
                assert circuit_breaker.state == CircuitState.OPEN
                assert result["result"] == "fallback"
        
        # Verify failure count doesn't exceed threshold + buffer
        assert failure_count <= circuit_breaker.failure_threshold + 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, migration_circuit_breaker):
        """Test circuit breaker recovery after timeout."""
        
        call_count = 0
        
        async def initially_failing_operation():
            nonlocal call_count
            call_count += 1
            
            # First few calls fail, then succeed
            if call_count <= 3:
                raise Exception("Initial failure")
            return {"status": "success", "result": "recovered"}
        
        async def fallback_operation():
            return {"status": "success", "result": "fallback"}
        
        # Trigger circuit to open
        for i in range(3):
            await migration_circuit_breaker.call(initially_failing_operation, fallback_operation)
        
        assert migration_circuit_breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(migration_circuit_breaker.recovery_timeout + 0.1)
        
        # Next call should attempt primary again (half-open)
        result = await migration_circuit_breaker.call(initially_failing_operation, fallback_operation)
        
        # Should have recovered
        assert result["result"] == "recovered"
        assert migration_circuit_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_backend_fallback(self):
        """Test circuit breaker with actual backend fallback scenario."""
        
        # This will fail initially - BackendCircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import BackendCircuitBreaker
        
        backend_cb = BackendCircuitBreaker(
            backend_name="hatchet",
            failure_threshold=2,
            recovery_timeout=1.0
        )
        
        hatchet_call_count = 0
        celery_call_count = 0
        
        async def hatchet_backend_call(*args, **kwargs):
            nonlocal hatchet_call_count
            hatchet_call_count += 1
            raise Exception("Hatchet service unavailable")
        
        async def celery_fallback_call(*args, **kwargs):
            nonlocal celery_call_count
            celery_call_count += 1
            return {"status": "success", "backend": "celery", "workflow_id": "celery_123"}
        
        # Execute multiple workflow requests
        results = []
        for i in range(5):
            # This will fail - execute_with_fallback method doesn't exist
            result = await backend_cb.execute_with_fallback(
                primary_call=hatchet_backend_call,
                fallback_call=celery_fallback_call,
                workflow_name="test_workflow",
                input_data={"test": f"data_{i}"}
            )
            results.append(result)
        
        # Verify circuit breaker behavior
        assert backend_cb.state == CircuitState.OPEN
        assert hatchet_call_count <= backend_cb.failure_threshold + 1
        assert celery_call_count == 5  # All requests served by fallback
        
        # All results should be from celery fallback
        for result in results:
            assert result["backend"] == "celery"
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics_collection(self):
        """Test circuit breaker metrics collection during operation."""
        
        # This will fail initially - MetricsCollectingCircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import MetricsCollectingCircuitBreaker
        
        metrics_cb = MetricsCollectingCircuitBreaker(
            name="test_circuit",
            failure_threshold=2,
            recovery_timeout=1.0
        )
        
        async def flaky_operation():
            import random
            if random.random() < 0.7:  # 70% failure rate
                raise Exception("Random failure")
            return {"status": "success"}
        
        async def reliable_fallback():
            return {"status": "success", "source": "fallback"}
        
        # Execute operations to generate metrics
        for i in range(20):
            await metrics_cb.call(flaky_operation, reliable_fallback)
            await asyncio.sleep(0.1)  # Small delay between calls
        
        # This will fail - get_metrics method doesn't exist
        metrics = metrics_cb.get_metrics()
        
        # Verify metrics are collected
        assert "total_calls" in metrics
        assert "successful_calls" in metrics
        assert "failed_calls" in metrics
        assert "circuit_open_count" in metrics
        assert "average_response_time" in metrics
        
        assert metrics["total_calls"] == 20
        assert metrics["successful_calls"] + metrics["failed_calls"] == 20
        assert metrics["circuit_open_count"] >= 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_concurrent_calls(self, circuit_breaker):
        """Test circuit breaker behavior under concurrent load."""
        
        concurrent_call_count = 0
        successful_calls = 0
        fallback_calls = 0
        
        async def load_test_operation():
            nonlocal concurrent_call_count
            concurrent_call_count += 1
            
            # Simulate some failures to trigger circuit breaker
            if concurrent_call_count <= 10:
                raise Exception("Load test failure")
            return {"status": "success", "call_id": concurrent_call_count}
        
        async def load_test_fallback():
            nonlocal fallback_calls
            fallback_calls += 1
            return {"status": "success", "source": "fallback"}
        
        # Execute concurrent calls
        tasks = [
            circuit_breaker.call(load_test_operation, load_test_fallback)
            for _ in range(50)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all calls completed (either success or fallback)
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == 50
        
        # Verify circuit breaker opened under load
        assert circuit_breaker.state == CircuitState.OPEN
        assert fallback_calls > 0  # Some calls should have used fallback

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_different_error_types(self, migration_circuit_breaker):
        """Test circuit breaker handling of different error types."""
        
        error_types = [
            ConnectionError("Connection failed"),
            TimeoutError("Operation timed out"), 
            ValueError("Invalid input"),
            RuntimeError("Runtime error"),
            Exception("Generic error")
        ]
        
        error_index = 0
        
        async def multi_error_operation():
            nonlocal error_index
            current_error = error_types[error_index % len(error_types)]
            error_index += 1
            raise current_error
        
        async def error_handling_fallback():
            return {"status": "success", "handled_error": True}
        
        # Execute operations with different error types
        for i in range(len(error_types) + 2):  # More than threshold
            result = await migration_circuit_breaker.call(
                multi_error_operation,
                error_handling_fallback
            )
            assert result["handled_error"] is True
        
        # Circuit should be open after multiple failures
        assert migration_circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_custom_failure_predicate(self):
        """Test circuit breaker with custom failure detection logic."""
        
        # This will fail initially - CustomCircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import CustomCircuitBreaker
        
        def custom_failure_predicate(exception: Exception) -> bool:
            # Only count ConnectionError and TimeoutError as failures
            return isinstance(exception, (ConnectionError, TimeoutError))
        
        custom_cb = CustomCircuitBreaker(
            failure_threshold=2,
            recovery_timeout=1.0,
            failure_predicate=custom_failure_predicate
        )
        
        call_count = 0
        
        async def selective_failing_operation():
            nonlocal call_count
            call_count += 1
            
            if call_count in [1, 2]:
                raise ValueError("This should not count as failure")
            elif call_count in [3, 4]:
                raise ConnectionError("This should count as failure")
            return {"status": "success"}
        
        async def selective_fallback():
            return {"status": "fallback"}
        
        # Execute operations
        for i in range(5):
            try:
                result = await custom_cb.call(selective_failing_operation, selective_fallback)
            except ValueError:
                # ValueError should not trigger circuit breaker
                pass
        
        # Circuit should be open only after ConnectionError failures
        assert custom_cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration_with_workflow_execution(self):
        """Test circuit breaker integration with actual workflow execution."""
        
        # This will fail initially - WorkflowCircuitBreaker doesn't exist
        from unstract.task_abstraction.circuit_breaker import WorkflowCircuitBreaker
        
        workflow_cb = WorkflowCircuitBreaker(
            workflow_name="document_processing",
            backend_name="hatchet",
            failure_threshold=3,
            recovery_timeout=2.0
        )
        
        execution_count = 0
        
        async def mock_workflow_execution(workflow_name, input_data, context):
            nonlocal execution_count
            execution_count += 1
            
            if execution_count <= 3:
                raise Exception(f"Workflow execution failed: {workflow_name}")
            
            return {
                "workflow_id": f"workflow_{execution_count}",
                "status": "completed",
                "results": {"processed": True}
            }
        
        async def fallback_workflow_execution(workflow_name, input_data, context):
            return {
                "workflow_id": f"fallback_workflow_{execution_count}",
                "status": "completed",
                "backend": "celery_fallback",
                "results": {"processed": True}
            }
        
        # Execute workflow requests
        results = []
        for i in range(6):
            # This will fail - execute_workflow_with_protection method doesn't exist
            result = await workflow_cb.execute_workflow_with_protection(
                primary_executor=mock_workflow_execution,
                fallback_executor=fallback_workflow_execution,
                workflow_name="document_processing",
                input_data={"document": f"doc_{i}.pdf"},
                context={"user_id": f"user_{i}"}
            )
            results.append(result)
        
        # Verify circuit breaker behavior
        assert workflow_cb.state == CircuitState.OPEN
        assert execution_count <= 4  # Should stop calling primary after threshold
        
        # Later results should be from fallback
        fallback_results = [r for r in results[-3:] if "fallback" in r.get("backend", "")]
        assert len(fallback_results) >= 1

    def test_circuit_breaker_interface_compliance(self):
        """Test that circuit breaker classes implement expected interfaces."""
        # This will fail initially - CircuitBreaker classes don't exist
        from unstract.task_abstraction.circuit_breaker import (
            CircuitBreaker, MigrationCircuitBreaker, BackendCircuitBreaker
        )
        
        # Check required methods exist on base CircuitBreaker
        required_methods = [
            'call', 'state', 'reset', 'get_metrics'
        ]
        
        for method_name in required_methods:
            assert hasattr(CircuitBreaker, method_name)
            
        # Check migration-specific methods
        migration_methods = ['execute_with_fallback']
        for method_name in migration_methods:
            assert hasattr(MigrationCircuitBreaker, method_name)
            
        # Check backend-specific methods
        backend_methods = ['execute_with_fallback']
        for method_name in backend_methods:
            assert hasattr(BackendCircuitBreaker, method_name)