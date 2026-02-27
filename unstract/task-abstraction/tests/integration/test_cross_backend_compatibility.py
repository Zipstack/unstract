"""
Cross-Backend Compatibility Integration Test (T011)

This test validates compatibility and data interchange between different backend
implementations (Celery, Hatchet, Temporal). These tests MUST FAIL initially (TDD approach).
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pytest
from unstract.task_abstraction.interfaces import TaskClient
from unstract.task_abstraction.models import (
    TaskConfig,
    TaskDefinition,
    WorkflowConfig,
    WorkflowDefinition,
)


class BackendType(Enum):
    """Backend types for compatibility testing."""

    CELERY = "celery"
    HATCHET = "hatchet"
    TEMPORAL = "temporal"


@dataclass
class CrossBackendTestCase:
    """Test case for cross-backend compatibility scenarios."""

    name: str
    source_backend: BackendType
    target_backend: BackendType
    workflow_definition: WorkflowDefinition
    test_data: dict[str, Any]
    compatibility_requirements: list[str]


@pytest.mark.integration
@pytest.mark.cross_backend_compatibility
class TestCrossBackendCompatibilityIntegration:
    """Integration tests for cross-backend compatibility."""

    @pytest.fixture
    def sample_workflow_definition(self) -> WorkflowDefinition:
        """Sample workflow definition for compatibility testing."""
        return WorkflowDefinition(
            config=WorkflowConfig(
                name="cross-backend-test-workflow",
                description="Test workflow for cross-backend compatibility",
                timeout_minutes=20,
            ),
            tasks=[
                TaskDefinition(
                    config=TaskConfig(name="data-extraction", timeout_minutes=5),
                    function_name="extract_data",
                    parents=[],
                ),
                TaskDefinition(
                    config=TaskConfig(name="data-transformation", timeout_minutes=8),
                    function_name="transform_data",
                    parents=["data-extraction"],
                ),
                TaskDefinition(
                    config=TaskConfig(name="data-validation", timeout_minutes=3),
                    function_name="validate_data",
                    parents=["data-transformation"],
                ),
                TaskDefinition(
                    config=TaskConfig(name="result-aggregation", timeout_minutes=4),
                    function_name="aggregate_results",
                    parents=["data-validation"],
                ),
            ],
        )

    @pytest.fixture
    def cross_backend_test_cases(
        self, sample_workflow_definition: WorkflowDefinition
    ) -> list[CrossBackendTestCase]:
        """Test cases for cross-backend compatibility scenarios."""
        return [
            CrossBackendTestCase(
                name="celery_to_hatchet_migration",
                source_backend=BackendType.CELERY,
                target_backend=BackendType.HATCHET,
                workflow_definition=sample_workflow_definition,
                test_data={"input_file": "test_document.pdf", "format": "json"},
                compatibility_requirements=[
                    "workflow_definition_compatibility",
                    "task_result_serialization",
                    "error_handling_parity",
                    "timeout_behavior_consistency",
                ],
            ),
            CrossBackendTestCase(
                name="hatchet_to_temporal_migration",
                source_backend=BackendType.HATCHET,
                target_backend=BackendType.TEMPORAL,
                workflow_definition=sample_workflow_definition,
                test_data={"input_data": {"records": 1000}, "batch_size": 100},
                compatibility_requirements=[
                    "workflow_definition_compatibility",
                    "async_task_execution",
                    "signal_handling",
                    "state_persistence",
                ],
            ),
            CrossBackendTestCase(
                name="temporal_to_celery_fallback",
                source_backend=BackendType.TEMPORAL,
                target_backend=BackendType.CELERY,
                workflow_definition=sample_workflow_definition,
                test_data={"complex_input": {"nested": {"data": "structure"}}},
                compatibility_requirements=[
                    "workflow_definition_compatibility",
                    "data_serialization_compatibility",
                    "error_propagation",
                    "result_format_consistency",
                ],
            ),
        ]

    @pytest.fixture
    async def backend_clients(self) -> dict[BackendType, TaskClient]:
        """Create backend clients for compatibility testing."""
        clients = {}

        # This will fail initially - backend clients don't exist
        from unstract.task_abstraction.backends.celery_backend import CeleryTaskClient
        from unstract.task_abstraction.backends.hatchet_backend import HatchetTaskClient
        from unstract.task_abstraction.backends.temporal_backend import TemporalTaskClient

        clients[BackendType.CELERY] = CeleryTaskClient(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/1",
        )

        clients[BackendType.HATCHET] = HatchetTaskClient(
            server_url="http://localhost:8080", token="test_token"
        )

        clients[BackendType.TEMPORAL] = TemporalTaskClient(
            host_port="localhost:7233", namespace="test-namespace"
        )

        # Initialize all clients
        for client in clients.values():
            await client.startup()

        yield clients

        # Cleanup
        for client in clients.values():
            await client.shutdown()

    @pytest.mark.asyncio
    async def test_workflow_definition_compatibility(
        self,
        backend_clients: dict[BackendType, TaskClient],
        cross_backend_test_cases: list[CrossBackendTestCase],
    ):
        """Test that workflow definitions are compatible across backends."""

        for test_case in cross_backend_test_cases:
            source_client = backend_clients[test_case.source_backend]
            target_client = backend_clients[test_case.target_backend]

            # Register workflow on source backend
            source_registration = await source_client.register_workflow(
                test_case.workflow_definition
            )
            assert (
                source_registration.success
            ), f"Failed to register on {test_case.source_backend}"

            # Register same workflow on target backend
            target_registration = await target_client.register_workflow(
                test_case.workflow_definition
            )
            assert (
                target_registration.success
            ), f"Failed to register on {test_case.target_backend}"

            # Verify workflow definitions are equivalent
            # This will fail - get_workflow_definition method doesn't exist
            source_definition = await source_client.get_workflow_definition(
                test_case.workflow_definition.config.name
            )
            target_definition = await target_client.get_workflow_definition(
                test_case.workflow_definition.config.name
            )

            # Compare key workflow properties
            assert source_definition.config.name == target_definition.config.name
            assert len(source_definition.tasks) == len(target_definition.tasks)

            # Verify task compatibility
            for i, (source_task, target_task) in enumerate(
                zip(source_definition.tasks, target_definition.tasks, strict=False)
            ):
                assert (
                    source_task.config.name == target_task.config.name
                ), f"Task {i} name mismatch: {source_task.config.name} != {target_task.config.name}"

    @pytest.mark.asyncio
    async def test_data_serialization_compatibility(
        self,
        backend_clients: dict[BackendType, TaskClient],
        cross_backend_test_cases: list[CrossBackendTestCase],
    ):
        """Test data serialization compatibility between backends."""

        test_data_variations = [
            {"simple": "string", "number": 123, "boolean": True},
            {"nested": {"level1": {"level2": {"data": "deep"}}}},
            {"list": [1, 2, 3, {"item": "value"}]},
            {"mixed": {"string": "text", "list": [1, 2], "dict": {"key": "value"}}},
            {"large_text": "x" * 10000},  # Large string
            {"unicode": "测试数据 🚀 ñoñó"},  # Unicode characters
        ]

        for test_case in cross_backend_test_cases:
            source_client = backend_clients[test_case.source_backend]
            target_client = backend_clients[test_case.target_backend]

            # Register workflow on both backends
            await source_client.register_workflow(test_case.workflow_definition)
            await target_client.register_workflow(test_case.workflow_definition)

            for i, test_data in enumerate(test_data_variations):
                # Execute on source backend
                source_workflow_id = await source_client.run_workflow_async(
                    test_case.workflow_definition.config.name, test_data
                )

                # Execute same data on target backend
                target_workflow_id = await target_client.run_workflow_async(
                    test_case.workflow_definition.config.name, test_data
                )

                # Wait for completion
                await asyncio.sleep(2)

                # Compare results
                source_result = await source_client.get_workflow_result(
                    source_workflow_id
                )
                target_result = await target_client.get_workflow_result(
                    target_workflow_id
                )

                # Results should have same structure (may have different backend-specific metadata)
                assert (
                    source_result.status == target_result.status
                ), f"Status mismatch for data variant {i}: {source_result.status} != {target_result.status}"

                # Task results should be compatible
                assert len(source_result.task_results) == len(
                    target_result.task_results
                ), f"Task result count mismatch for data variant {i}"

    @pytest.mark.asyncio
    async def test_error_handling_compatibility(
        self,
        backend_clients: dict[BackendType, TaskClient],
        sample_workflow_definition: WorkflowDefinition,
    ):
        """Test error handling compatibility across backends."""

        error_scenarios = [
            {
                "name": "task_timeout",
                "workflow_override": WorkflowDefinition(
                    config=WorkflowConfig(
                        name="timeout-test-workflow",
                        description="Test timeout handling",
                        timeout_minutes=1,
                    ),
                    tasks=[
                        TaskDefinition(
                            config=TaskConfig(
                                name="timeout-task",
                                timeout_minutes=0.1,  # Very short timeout
                            ),
                            function_name="slow_task",
                            parents=[],
                        )
                    ],
                ),
                "input_data": {"delay_seconds": 10},
                "expected_error_type": "TimeoutError",
            },
            {
                "name": "task_failure",
                "workflow_override": sample_workflow_definition,
                "input_data": {"force_error": True, "error_type": "ValueError"},
                "expected_error_type": "ValueError",
            },
            {
                "name": "invalid_input",
                "workflow_override": sample_workflow_definition,
                "input_data": None,  # Invalid input
                "expected_error_type": "ValidationError",
            },
        ]

        for scenario in error_scenarios:
            for backend_type, client in backend_clients.items():
                # Register workflow
                await client.register_workflow(scenario["workflow_override"])

                # Execute workflow with error condition
                try:
                    workflow_id = await client.run_workflow_async(
                        scenario["workflow_override"].config.name, scenario["input_data"]
                    )

                    # Wait for completion/failure
                    await asyncio.sleep(3)

                    result = await client.get_workflow_result(workflow_id)

                    # Should be failed status
                    assert (
                        result.status == "failed"
                    ), f"Backend {backend_type} should have failed status for scenario '{scenario['name']}'"

                    # Error information should be available
                    assert (
                        result.error is not None
                    ), f"Backend {backend_type} should have error information for scenario '{scenario['name']}'"

                except Exception as e:
                    # Exception during execution is also valid error handling
                    error_type_name = type(e).__name__
                    assert (
                        scenario["expected_error_type"] in str(e)
                        or scenario["expected_error_type"] == error_type_name
                    ), f"Backend {backend_type} unexpected error type for scenario '{scenario['name']}': {e}"

    @pytest.mark.asyncio
    async def test_result_format_consistency(
        self,
        backend_clients: dict[BackendType, TaskClient],
        sample_workflow_definition: WorkflowDefinition,
    ):
        """Test result format consistency across backends."""

        # Register workflow on all backends
        for client in backend_clients.values():
            await client.register_workflow(sample_workflow_definition)

        test_input = {"test_data": "compatibility_check"}
        workflow_results = {}

        # Execute on all backends
        for backend_type, client in backend_clients.items():
            workflow_id = await client.run_workflow_async(
                sample_workflow_definition.config.name, test_input
            )

            # Wait for completion
            await asyncio.sleep(2)

            result = await client.get_workflow_result(workflow_id)
            workflow_results[backend_type] = result

        # Compare result structures
        result_list = list(workflow_results.values())
        base_result = result_list[0]

        for i, other_result in enumerate(result_list[1:], 1):
            backend_name = list(workflow_results.keys())[i]

            # Check required fields exist
            required_fields = [
                "workflow_id",
                "status",
                "task_results",
                "created_at",
                "completed_at",
            ]
            for field in required_fields:
                assert hasattr(
                    other_result, field
                ), f"Backend {backend_name} missing required field: {field}"
                assert hasattr(
                    base_result, field
                ), f"Base backend missing required field: {field}"

            # Status should be comparable
            assert (
                other_result.status == base_result.status
            ), f"Status mismatch between backends: {other_result.status} != {base_result.status}"

            # Task results should have same structure
            assert (
                len(other_result.task_results) == len(base_result.task_results)
            ), f"Task result count mismatch: {len(other_result.task_results)} != {len(base_result.task_results)}"

    @pytest.mark.asyncio
    async def test_backend_migration_data_transfer(
        self,
        backend_clients: dict[BackendType, TaskClient],
        sample_workflow_definition: WorkflowDefinition,
    ):
        """Test data transfer during backend migration scenarios."""

        # This will fail initially - BackendMigrationManager doesn't exist
        from unstract.task_abstraction.migration_manager import BackendMigrationManager

        migration_manager = BackendMigrationManager()

        # Start workflow on source backend (Celery)
        source_client = backend_clients[BackendType.CELERY]
        await source_client.register_workflow(sample_workflow_definition)

        source_workflow_id = await source_client.run_workflow_async(
            sample_workflow_definition.config.name,
            {"migration_test": True, "stage": "initial"},
        )

        # Wait for partial execution
        await asyncio.sleep(1)

        # This will fail - migrate_running_workflow method doesn't exist
        migration_result = await migration_manager.migrate_running_workflow(
            source_workflow_id=source_workflow_id,
            source_backend=BackendType.CELERY,
            target_backend=BackendType.HATCHET,
            migration_strategy="checkpoint_resume",
        )

        assert migration_result.success, "Migration should succeed"
        assert (
            migration_result.target_workflow_id is not None
        ), "Target workflow ID should be set"

        # Verify target workflow continues execution
        target_client = backend_clients[BackendType.HATCHET]
        target_result = await target_client.get_workflow_result(
            migration_result.target_workflow_id
        )

        # Should eventually complete
        max_wait = 10
        while target_result.status == "running" and max_wait > 0:
            await asyncio.sleep(1)
            target_result = await target_client.get_workflow_result(
                migration_result.target_workflow_id
            )
            max_wait -= 1

        assert target_result.status == "completed", "Migrated workflow should complete"

    @pytest.mark.asyncio
    async def test_concurrent_multi_backend_execution(
        self,
        backend_clients: dict[BackendType, TaskClient],
        sample_workflow_definition: WorkflowDefinition,
    ):
        """Test concurrent execution across multiple backends."""

        # Register workflow on all backends
        for client in backend_clients.values():
            await client.register_workflow(sample_workflow_definition)

        # Execute same workflow concurrently on all backends
        concurrent_tasks = []
        for backend_type, client in backend_clients.items():
            for i in range(3):  # 3 concurrent executions per backend
                task = client.run_workflow_async(
                    sample_workflow_definition.config.name,
                    {"backend": backend_type.value, "execution": i},
                )
                concurrent_tasks.append((backend_type, task))

        # Wait for all to start
        workflow_ids = []
        for backend_type, task in concurrent_tasks:
            workflow_id = await task
            workflow_ids.append((backend_type, workflow_id))

        # Wait for completion
        await asyncio.sleep(5)

        # Verify all completed successfully
        completed_count = 0
        for backend_type, workflow_id in workflow_ids:
            client = backend_clients[backend_type]
            result = await client.get_workflow_result(workflow_id)

            if result.status == "completed":
                completed_count += 1
            elif result.status == "failed":
                pytest.fail(f"Workflow failed on {backend_type}: {result.error}")

        # Most executions should complete successfully
        expected_completions = len(workflow_ids) * 0.8  # Allow for 20% failure rate
        assert (
            completed_count >= expected_completions
        ), f"Expected at least {expected_completions} completions, got {completed_count}"

    @pytest.mark.asyncio
    async def test_backend_specific_feature_compatibility(
        self, backend_clients: dict[BackendType, TaskClient]
    ):
        """Test backend-specific feature compatibility and graceful degradation."""

        backend_features = {
            BackendType.CELERY: {
                "features": ["task_routing", "retry_policy", "rate_limiting"],
                "test_workflow": WorkflowDefinition(
                    config=WorkflowConfig(
                        name="celery-specific-workflow",
                        description="Test Celery-specific features",
                        timeout_minutes=10,
                    ),
                    tasks=[
                        TaskDefinition(
                            config=TaskConfig(
                                name="routed-task",
                                timeout_minutes=5,
                                queue="high_priority",
                                routing_key="urgent.tasks",
                            ),
                            function_name="priority_task",
                            parents=[],
                        )
                    ],
                ),
            },
            BackendType.HATCHET: {
                "features": ["step_functions", "dynamic_workflows", "dag_optimization"],
                "test_workflow": WorkflowDefinition(
                    config=WorkflowConfig(
                        name="hatchet-specific-workflow",
                        description="Test Hatchet-specific features",
                        timeout_minutes=10,
                    ),
                    tasks=[
                        TaskDefinition(
                            config=TaskConfig(
                                name="dynamic-step",
                                timeout_minutes=5,
                                step_config={"dynamic": True, "optimization": "dag"},
                            ),
                            function_name="dynamic_task",
                            parents=[],
                        )
                    ],
                ),
            },
            BackendType.TEMPORAL: {
                "features": ["signals", "queries", "activities", "workflows"],
                "test_workflow": WorkflowDefinition(
                    config=WorkflowConfig(
                        name="temporal-specific-workflow",
                        description="Test Temporal-specific features",
                        timeout_minutes=10,
                    ),
                    tasks=[
                        TaskDefinition(
                            config=TaskConfig(
                                name="signal-aware-task",
                                timeout_minutes=5,
                                signals=["pause", "resume"],
                                queries=["get_status"],
                            ),
                            function_name="signal_task",
                            parents=[],
                        )
                    ],
                ),
            },
        }

        for backend_type, config in backend_features.items():
            client = backend_clients[backend_type]

            # Register backend-specific workflow
            registration_result = await client.register_workflow(config["test_workflow"])
            assert (
                registration_result.success
            ), f"Failed to register {backend_type} specific workflow"

            # Execute workflow
            workflow_id = await client.run_workflow_async(
                config["test_workflow"].config.name, {"test_features": config["features"]}
            )

            # Wait for completion
            await asyncio.sleep(3)

            result = await client.get_workflow_result(workflow_id)

            # Should handle backend-specific features gracefully
            assert (
                result.status in ["completed", "running"]
            ), f"Backend {backend_type} failed to handle specific features: {result.error}"

    def test_cross_backend_interface_compliance(self):
        """Test that all backends implement consistent interfaces."""
        # This will fail initially - backend clients don't exist
        from unstract.task_abstraction.backends.celery_backend import CeleryTaskClient
        from unstract.task_abstraction.backends.hatchet_backend import HatchetTaskClient
        from unstract.task_abstraction.backends.temporal_backend import TemporalTaskClient
        from unstract.task_abstraction.interfaces import TaskClient

        backend_classes = [CeleryTaskClient, HatchetTaskClient, TemporalTaskClient]

        # All should implement TaskClient interface
        for backend_class in backend_classes:
            assert issubclass(
                backend_class, TaskClient
            ), f"{backend_class.__name__} should implement TaskClient interface"

        # Check required methods exist on all backends
        required_methods = [
            "startup",
            "shutdown",
            "register_workflow",
            "run_workflow_async",
            "get_workflow_result",
            "get_task_result",
            "cancel_workflow",
        ]

        for backend_class in backend_classes:
            for method_name in required_methods:
                assert hasattr(
                    backend_class, method_name
                ), f"{backend_class.__name__} missing required method: {method_name}"
                assert callable(
                    getattr(backend_class, method_name)
                ), f"{backend_class.__name__}.{method_name} should be callable"
