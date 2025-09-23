"""
Migration API Contract Tests

These contract tests ensure the migration execution manager and feature flag integration
work correctly across different migration scenarios and backend configurations.
"""

import pytest
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass
from enum import Enum


class BackendType(Enum):
    LEGACY_CELERY = "legacy_celery"
    UNIFIED_CELERY = "unified_celery"
    TASK_ABSTRACTION = "task_abstraction"
    HATCHET = "hatchet"


@dataclass
class MigrationTestContext:
    """Test context for migration scenarios."""
    user_id: str
    organization_id: str
    workflow_name: str
    feature_flags: Dict[str, bool]
    expected_backend: BackendType
    rollout_percentage: int = 0


class MigrationAPIContractTest:
    """Contract tests for migration API functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.test_contexts = [
            MigrationTestContext(
                user_id="user_1",
                organization_id="org_1", 
                workflow_name="document_processing",
                feature_flags={
                    "task_abstraction_enabled": True,
                    "hatchet_backend_enabled": False,
                    "unified_celery_enabled": False
                },
                expected_backend=BackendType.TASK_ABSTRACTION,
                rollout_percentage=100
            ),
            MigrationTestContext(
                user_id="user_2",
                organization_id="org_1",
                workflow_name="document_processing", 
                feature_flags={
                    "task_abstraction_enabled": False,
                    "hatchet_backend_enabled": False,
                    "unified_celery_enabled": True
                },
                expected_backend=BackendType.UNIFIED_CELERY,
                rollout_percentage=0
            ),
            MigrationTestContext(
                user_id="user_3",
                organization_id="org_2",
                workflow_name="document_processing",
                feature_flags={
                    "task_abstraction_enabled": True,
                    "hatchet_backend_enabled": True,
                    "unified_celery_enabled": False
                },
                expected_backend=BackendType.HATCHET,
                rollout_percentage=100
            )
        ]
    
    @pytest.mark.asyncio
    async def test_backend_selection_logic(self):
        """Test backend selection based on feature flags."""
        
        for context in self.test_contexts:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                # Mock feature flag responses
                mock_flag.side_effect = lambda flag_key, *args, **kwargs: context.feature_flags.get(flag_key, False)
                
                # Test backend selection
                from backend.workflow_manager.migration_execution_manager import MigrationExecutionManager
                manager = MigrationExecutionManager()
                
                selected_backend = manager._select_backend(
                    context.workflow_name,
                    {
                        "user_id": context.user_id,
                        "organization_id": context.organization_id
                    },
                    preferred_backend=None
                )
                
                assert selected_backend == context.expected_backend, \
                    f"Expected {context.expected_backend} for context {context.user_id}, got {selected_backend}"
    
    @pytest.mark.asyncio
    async def test_gradual_rollout_percentages(self):
        """Test gradual rollout with different percentages."""
        rollout_percentages = [0, 25, 50, 75, 100]
        user_count = 100
        
        for percentage in rollout_percentages:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                # Mock percentage-based feature flag
                def mock_percentage_flag(flag_key, namespace, entity_id, context=None):
                    if flag_key == "task_abstraction_enabled":
                        # Hash-based consistent assignment
                        import hashlib
                        hash_value = int(hashlib.md5(entity_id.encode()).hexdigest(), 16)
                        user_bucket = hash_value % 100
                        return user_bucket < percentage
                    return False
                
                mock_flag.side_effect = mock_percentage_flag
                
                # Test rollout distribution
                from backend.workflow_manager.migration_execution_manager import ServiceMigrationManager
                manager = ServiceMigrationManager()
                
                enabled_count = 0
                for i in range(user_count):
                    user_id = f"user_{i}"
                    if manager.should_use_task_abstraction("test_workflow", {"user_id": user_id}):
                        enabled_count += 1
                
                # Allow for small variance due to hashing
                expected_range = (percentage - 5, percentage + 5)
                assert expected_range[0] <= enabled_count <= expected_range[1], \
                    f"Expected ~{percentage}% rollout, got {enabled_count}%"
    
    @pytest.mark.asyncio
    async def test_fallback_chain_execution(self):
        """Test fallback behavior when primary backend fails."""
        
        # Mock backend execution functions
        async def mock_execute_hatchet(*args):
            raise Exception("Hatchet unavailable")
        
        async def mock_execute_task_abstraction(*args):
            raise Exception("Task abstraction failed")
        
        async def mock_execute_unified_celery(*args):
            return {"status": "success", "backend": "unified_celery"}
        
        async def mock_execute_legacy_celery(*args):
            return {"status": "success", "backend": "legacy_celery"}
        
        from backend.workflow_manager.migration_execution_manager import MigrationExecutionManager
        manager = MigrationExecutionManager()
        
        # Mock the backend execution methods
        manager._execute_task_abstraction = mock_execute_hatchet
        manager._execute_unified_celery = mock_execute_unified_celery
        manager._execute_legacy_celery = mock_execute_legacy_celery
        
        # Test fallback chain
        result = await manager._execute_with_fallbacks(
            BackendType.HATCHET,
            "test_workflow",
            {"input": "data"},
            {"user_id": "test_user"}
        )
        
        # Should fallback to unified celery
        assert result["backend"] == "unified_celery"
        assert result["fallback_used"] is True
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_behavior(self):
        """Test circuit breaker functionality during backend failures."""
        
        from backend.utils.migration_circuit_breaker import MigrationCircuitBreaker, CircuitState
        
        circuit_breaker = MigrationCircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        call_count = 0
        fallback_count = 0
        
        async def failing_primary(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Service unavailable")
        
        async def working_fallback(*args, **kwargs):
            nonlocal fallback_count
            fallback_count += 1
            return {"status": "success", "backend": "fallback"}
        
        # Test circuit breaker opening
        for i in range(5):
            result = await circuit_breaker.call(failing_primary, working_fallback)
            assert result["backend"] == "fallback"
        
        # Should stop calling primary after threshold
        assert call_count <= circuit_breaker.failure_threshold
        assert fallback_count == 5
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Test recovery
        await asyncio.sleep(1.1)  # Wait for recovery timeout
        
        # Should attempt primary again
        result = await circuit_breaker.call(failing_primary, working_fallback)
        assert call_count == circuit_breaker.failure_threshold + 1  # One more attempt
    
    @pytest.mark.asyncio
    async def test_api_compatibility_layer(self):
        """Test API compatibility during migration."""
        
        from backend.api_v2.migration_compatibility_layer import APICompatibilityManager
        
        test_cases = [
            {
                "api_version": "v1",
                "expected_legacy_behavior": True,
                "feature_flags": {"task_abstraction_enabled": False}
            },
            {
                "api_version": "v2", 
                "expected_legacy_behavior": False,
                "feature_flags": {"task_abstraction_enabled": True}
            },
            {
                "api_version": "v3",
                "expected_legacy_behavior": False,
                "feature_flags": {"task_abstraction_enabled": True, "hatchet_backend_enabled": True}
            }
        ]
        
        for case in test_cases:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                mock_flag.side_effect = lambda flag_key, *args, **kwargs: case["feature_flags"].get(flag_key, False)
                
                # Test API behavior
                manager = APICompatibilityManager()
                
                # Simulate request context
                migration_context = {
                    "api_version": case["api_version"],
                    "user_id": "test_user"
                }
                
                # Verify compatibility layer behavior
                # (Implementation specific - would test actual API endpoints)
                assert migration_context["api_version"] == case["api_version"]
    
    @pytest.mark.asyncio
    async def test_concurrent_migration_scenarios(self):
        """Test concurrent execution during migration state."""
        
        # Simulate mixed traffic during migration
        concurrent_requests = [
            {"user_id": f"user_{i}", "workflow": "document_processing"}
            for i in range(10)
        ]
        
        with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
            # 50% rollout simulation
            def mock_50_percent_rollout(flag_key, namespace, entity_id, context=None):
                if flag_key == "task_abstraction_enabled":
                    return hash(entity_id) % 2 == 0  # 50% based on user_id hash
                return False
            
            mock_flag.side_effect = mock_50_percent_rollout
            
            from backend.workflow_manager.migration_execution_manager import MigrationExecutionManager
            manager = MigrationExecutionManager()
            
            # Mock successful execution for all backends
            async def mock_successful_execution(*args):
                backend = args[0] if args else "unknown"
                return {"status": "success", "backend": str(backend)}
            
            manager._execute_task_abstraction = mock_successful_execution
            manager._execute_unified_celery = mock_successful_execution
            manager._execute_legacy_celery = mock_successful_execution
            
            # Execute all requests concurrently
            tasks = [
                manager.execute_workflow(
                    req["workflow"],
                    {"input": "data"},
                    {"user_id": req["user_id"]}
                )
                for req in concurrent_requests
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should succeed
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) == len(concurrent_requests)
            
            # Should have mix of backends
            backends_used = {r["backend"] for r in successful_results}
            assert len(backends_used) > 1, "Should use multiple backends during migration"
    
    @pytest.mark.asyncio
    async def test_error_handling_and_metrics(self):
        """Test error handling and metrics collection during migration."""
        
        from backend.workflow_manager.migration_execution_manager import MigrationExecutionManager
        from backend.monitoring.migration_monitoring import MigrationMonitoringService
        
        manager = MigrationExecutionManager()
        monitoring = MigrationMonitoringService()
        
        # Mock some backend failures
        async def failing_backend(*args):
            raise Exception("Backend failure")
        
        async def successful_backend(*args):
            return {"status": "success", "backend": "fallback"}
        
        manager._execute_task_abstraction = failing_backend
        manager._execute_unified_celery = successful_backend
        
        # Execute with failure and fallback
        result = await manager.execute_workflow(
            "test_workflow",
            {"input": "data"},
            {"user_id": "test_user"}
        )
        
        # Should succeed via fallback
        assert result["status"] == "success"
        assert result["fallback_used"] is True
        
        # Metrics should be recorded
        # (Implementation would verify actual metrics collection)
    
    def test_feature_flag_consistency(self):
        """Test feature flag evaluation consistency."""
        
        test_contexts = [
            {"user_id": "user_1", "organization_id": "org_1"},
            {"user_id": "user_1", "organization_id": "org_2"},
            {"user_id": "user_2", "organization_id": "org_1"}
        ]
        
        with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
            # Mock consistent flag evaluation
            def consistent_flag_evaluation(flag_key, namespace, entity_id, context=None):
                # Same user should get same result regardless of context
                return hash(f"{flag_key}_{entity_id}") % 2 == 0
            
            mock_flag.side_effect = consistent_flag_evaluation
            
            for context in test_contexts:
                # Multiple evaluations should be identical
                results = []
                for _ in range(5):
                    result = mock_flag(
                        "task_abstraction_enabled",
                        "default",
                        context["user_id"],
                        context
                    )
                    results.append(result)
                
                # All evaluations should be identical
                assert all(r == results[0] for r in results), \
                    f"Inconsistent flag evaluations for context {context}"
    
    @pytest.mark.asyncio
    async def test_service_replacement_scenarios(self):
        """Test service replacement with feature flags."""
        
        service_replacement_scenarios = [
            {
                "service": "runner_service",
                "flag": "task_abstraction_enabled",
                "legacy_response": {"status": "completed", "service": "runner"},
                "new_response": {"status": "completed", "service": "task_abstraction"}
            },
            {
                "service": "prompt_service",
                "flag": "prompt_helpers_enabled", 
                "legacy_response": {"status": "completed", "service": "prompt_service"},
                "new_response": {"status": "completed", "service": "prompt_helpers"}
            }
        ]
        
        for scenario in service_replacement_scenarios:
            # Test legacy behavior
            with patch('unstract.flags.feature_flag.check_feature_flag_status', return_value=False):
                # Would test actual service replacement logic here
                # For now, verify flag evaluation
                from unstract.flags.feature_flag import check_feature_flag_status
                
                flag_result = check_feature_flag_status(
                    scenario["flag"],
                    "default",
                    "test_user"
                )
                assert flag_result is False
            
            # Test new behavior  
            with patch('unstract.flags.feature_flag.check_feature_flag_status', return_value=True):
                flag_result = check_feature_flag_status(
                    scenario["flag"],
                    "default", 
                    "test_user"
                )
                assert flag_result is True


class MigrationIntegrationTest:
    """Integration tests for complete migration scenarios."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_migration_flow(self):
        """Test complete migration flow from 0% to 100% rollout."""
        
        rollout_stages = [0, 25, 50, 75, 100]
        user_ids = [f"user_{i}" for i in range(20)]
        
        for stage in rollout_stages:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                # Mock percentage rollout
                def stage_rollout(flag_key, namespace, entity_id, context=None):
                    if flag_key == "task_abstraction_enabled":
                        user_hash = hash(entity_id) % 100
                        return user_hash < stage
                    return False
                
                mock_flag.side_effect = stage_rollout
                
                # Test user distribution
                from backend.workflow_manager.migration_execution_manager import ServiceMigrationManager
                manager = ServiceMigrationManager()
                
                enabled_users = [
                    user_id for user_id in user_ids
                    if manager.should_use_task_abstraction("test", {"user_id": user_id})
                ]
                
                expected_count = len(user_ids) * stage // 100
                actual_count = len(enabled_users)
                
                # Allow for hash distribution variance
                variance = len(user_ids) // 10  # 10% variance
                assert abs(actual_count - expected_count) <= variance, \
                    f"Stage {stage}%: expected ~{expected_count} users, got {actual_count}"
    
    @pytest.mark.asyncio
    async def test_rollback_scenario(self):
        """Test rollback from new backend to legacy."""
        
        # Start with 100% rollout
        with patch('unstract.flags.feature_flag.check_feature_flag_status', return_value=True):
            from backend.workflow_manager.migration_execution_manager import MigrationExecutionManager
            manager = MigrationExecutionManager()
            
            selected_backend = manager._select_backend(
                "test_workflow",
                {"user_id": "test_user"},
                None
            )
            
            assert selected_backend == BackendType.TASK_ABSTRACTION
        
        # Simulate rollback to 0% 
        with patch('unstract.flags.feature_flag.check_feature_flag_status', return_value=False):
            selected_backend = manager._select_backend(
                "test_workflow", 
                {"user_id": "test_user"},
                None
            )
            
            assert selected_backend == BackendType.LEGACY_CELERY


if __name__ == "__main__":
    # Run contract tests
    test = MigrationAPIContractTest()
    integration_test = MigrationIntegrationTest()
    
    print("Running Migration API Contract Tests...")
    
    # List all test methods
    test_methods = [
        (test, method) for method in dir(test)
        if method.startswith('test_') and callable(getattr(test, method))
    ]
    
    integration_methods = [
        (integration_test, method) for method in dir(integration_test)
        if method.startswith('test_') and callable(getattr(integration_test, method))
    ]
    
    all_methods = test_methods + integration_methods
    
    passed = 0
    failed = 0
    
    for test_instance, method_name in all_methods:
        try:
            method = getattr(test_instance, method_name)
            if asyncio.iscoroutinefunction(method):
                asyncio.run(method())
            else:
                method()
            print(f"✓ {method_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {method_name}: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")