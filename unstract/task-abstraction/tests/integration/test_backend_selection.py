"""
Backend Selection Logic Integration Test (T008)

This test validates backend selection logic based on feature flags, user contexts,
and rollout configurations. These tests MUST FAIL initially (TDD approach).
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass
from enum import Enum

from unstract.task_abstraction.interfaces import TaskClient


class BackendType(Enum):
    """Available backend types."""
    LEGACY_CELERY = "legacy_celery"
    UNIFIED_CELERY = "unified_celery"
    TASK_ABSTRACTION = "task_abstraction"
    HATCHET = "hatchet"
    TEMPORAL = "temporal"


@dataclass
class BackendSelectionTestCase:
    """Test case for backend selection scenarios."""
    name: str
    feature_flags: Dict[str, bool]
    user_context: Dict[str, Any]
    rollout_percentage: int
    expected_backend: BackendType
    expected_fallback_chain: List[BackendType]


@pytest.mark.integration
@pytest.mark.backend_selection
class TestBackendSelectionIntegration:
    """Integration tests for backend selection logic."""

    @pytest.fixture
    def backend_selection_test_cases(self) -> List[BackendSelectionTestCase]:
        """Test cases for backend selection scenarios."""
        return [
            BackendSelectionTestCase(
                name="task_abstraction_enabled_100_percent",
                feature_flags={"task_abstraction_enabled": True},
                user_context={"user_id": "user_1", "organization_id": "org_1"},
                rollout_percentage=100,
                expected_backend=BackendType.TASK_ABSTRACTION,
                expected_fallback_chain=[
                    BackendType.TASK_ABSTRACTION,
                    BackendType.UNIFIED_CELERY,
                    BackendType.LEGACY_CELERY
                ]
            ),
            BackendSelectionTestCase(
                name="hatchet_backend_enabled",
                feature_flags={
                    "task_abstraction_enabled": True,
                    "hatchet_backend_enabled": True
                },
                user_context={"user_id": "user_2", "organization_id": "org_2"},
                rollout_percentage=100,
                expected_backend=BackendType.HATCHET,
                expected_fallback_chain=[
                    BackendType.HATCHET,
                    BackendType.TASK_ABSTRACTION,
                    BackendType.UNIFIED_CELERY,
                    BackendType.LEGACY_CELERY
                ]
            ),
            BackendSelectionTestCase(
                name="unified_celery_only",
                feature_flags={"unified_celery_enabled": True},
                user_context={"user_id": "user_3", "organization_id": "org_1"},
                rollout_percentage=100,
                expected_backend=BackendType.UNIFIED_CELERY,
                expected_fallback_chain=[
                    BackendType.UNIFIED_CELERY,
                    BackendType.LEGACY_CELERY
                ]
            ),
            BackendSelectionTestCase(
                name="legacy_fallback_all_disabled",
                feature_flags={},
                user_context={"user_id": "user_4", "organization_id": "org_3"},
                rollout_percentage=0,
                expected_backend=BackendType.LEGACY_CELERY,
                expected_fallback_chain=[BackendType.LEGACY_CELERY]
            ),
            BackendSelectionTestCase(
                name="temporal_experimental",
                feature_flags={
                    "task_abstraction_enabled": True,
                    "temporal_backend_enabled": True
                },
                user_context={"user_id": "user_5", "organization_id": "experimental_org"},
                rollout_percentage=5,
                expected_backend=BackendType.TEMPORAL,
                expected_fallback_chain=[
                    BackendType.TEMPORAL,
                    BackendType.TASK_ABSTRACTION,
                    BackendType.UNIFIED_CELERY,
                    BackendType.LEGACY_CELERY
                ]
            )
        ]

    @pytest.fixture
    async def backend_selector(self):
        """Create backend selector for testing."""
        # This will fail initially - BackendSelector doesn't exist
        from unstract.task_abstraction.migration_manager import BackendSelector
        return BackendSelector()

    @pytest.mark.asyncio
    async def test_backend_selection_by_feature_flags(
        self,
        backend_selector,
        backend_selection_test_cases: List[BackendSelectionTestCase]
    ):
        """Test backend selection based on feature flags."""
        
        for test_case in backend_selection_test_cases:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                # Mock feature flag responses
                def mock_flag_response(flag_key, namespace, entity_id, context=None):
                    return test_case.feature_flags.get(flag_key, False)
                
                mock_flag.side_effect = mock_flag_response
                
                # This will fail - select_backend method doesn't exist
                selected_backend = await backend_selector.select_backend(
                    workflow_name="test_workflow",
                    user_context=test_case.user_context,
                    preferred_backend=None
                )
                
                assert selected_backend == test_case.expected_backend, \
                    f"Test case '{test_case.name}': expected {test_case.expected_backend}, got {selected_backend}"

    @pytest.mark.asyncio
    async def test_rollout_percentage_distribution(self, backend_selector):
        """Test rollout percentage distribution across users."""
        
        rollout_scenarios = [
            {"percentage": 0, "expected_range": (0, 5)},
            {"percentage": 25, "expected_range": (20, 30)},
            {"percentage": 50, "expected_range": (45, 55)},
            {"percentage": 75, "expected_range": (70, 80)},
            {"percentage": 100, "expected_range": (95, 100)}
        ]
        
        user_count = 100
        
        for scenario in rollout_scenarios:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                # Mock percentage-based rollout
                def mock_percentage_rollout(flag_key, namespace, entity_id, context=None):
                    if flag_key == "task_abstraction_enabled":
                        import hashlib
                        hash_value = int(hashlib.md5(entity_id.encode()).hexdigest(), 16)
                        user_bucket = hash_value % 100
                        return user_bucket < scenario["percentage"]
                    return False
                
                mock_flag.side_effect = mock_percentage_rollout
                
                enabled_count = 0
                for i in range(user_count):
                    user_id = f"user_{i}"
                    selected_backend = await backend_selector.select_backend(
                        workflow_name="test_workflow",
                        user_context={"user_id": user_id, "organization_id": "test_org"}
                    )
                    
                    if selected_backend == BackendType.TASK_ABSTRACTION:
                        enabled_count += 1
                
                expected_min, expected_max = scenario["expected_range"]
                assert expected_min <= enabled_count <= expected_max, \
                    f"Rollout {scenario['percentage']}%: expected {expected_min}-{expected_max}, got {enabled_count}"

    @pytest.mark.asyncio
    async def test_organization_based_selection(self, backend_selector):
        """Test organization-based backend selection."""
        
        org_test_cases = [
            {
                "organization_id": "beta_org",
                "expected_backend": BackendType.HATCHET,
                "feature_flags": {
                    "task_abstraction_enabled": True,
                    "hatchet_backend_enabled": True
                }
            },
            {
                "organization_id": "stable_org",
                "expected_backend": BackendType.TASK_ABSTRACTION,
                "feature_flags": {"task_abstraction_enabled": True}
            },
            {
                "organization_id": "legacy_org",
                "expected_backend": BackendType.LEGACY_CELERY,
                "feature_flags": {}
            }
        ]
        
        for case in org_test_cases:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                def mock_org_based_flags(flag_key, namespace, entity_id, context=None):
                    org_id = context.get("organization_id") if context else None
                    
                    # Organization-specific logic
                    if org_id == "beta_org" and flag_key == "hatchet_backend_enabled":
                        return True
                    elif org_id == "stable_org" and flag_key == "task_abstraction_enabled":
                        return True
                    
                    return case["feature_flags"].get(flag_key, False)
                
                mock_flag.side_effect = mock_org_based_flags
                
                selected_backend = await backend_selector.select_backend(
                    workflow_name="test_workflow",
                    user_context={
                        "user_id": "test_user",
                        "organization_id": case["organization_id"]
                    }
                )
                
                assert selected_backend == case["expected_backend"], \
                    f"Org {case['organization_id']}: expected {case['expected_backend']}, got {selected_backend}"

    @pytest.mark.asyncio
    async def test_fallback_chain_construction(
        self,
        backend_selector,
        backend_selection_test_cases: List[BackendSelectionTestCase]
    ):
        """Test fallback chain construction based on enabled backends."""
        
        for test_case in backend_selection_test_cases:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                def mock_flag_response(flag_key, namespace, entity_id, context=None):
                    return test_case.feature_flags.get(flag_key, False)
                
                mock_flag.side_effect = mock_flag_response
                
                # This will fail - get_fallback_chain method doesn't exist
                fallback_chain = await backend_selector.get_fallback_chain(
                    user_context=test_case.user_context
                )
                
                assert fallback_chain == test_case.expected_fallback_chain, \
                    f"Test case '{test_case.name}': expected chain {test_case.expected_fallback_chain}, got {fallback_chain}"

    @pytest.mark.asyncio
    async def test_backend_availability_checking(self, backend_selector):
        """Test backend availability checking before selection."""
        
        # Mock backend availability
        backend_availability = {
            BackendType.HATCHET: False,  # Unavailable
            BackendType.TASK_ABSTRACTION: True,
            BackendType.UNIFIED_CELERY: True,
            BackendType.LEGACY_CELERY: True
        }
        
        with patch('unstract.flags.feature_flag.check_feature_flag_status', return_value=True):
            # Mock backend health checks
            async def mock_check_backend_availability(backend_type):
                return backend_availability.get(backend_type, False)
            
            # This will fail - check_backend_availability method doesn't exist
            backend_selector.check_backend_availability = mock_check_backend_availability
            
            selected_backend = await backend_selector.select_backend(
                workflow_name="test_workflow",
                user_context={"user_id": "test_user", "organization_id": "test_org"},
                check_availability=True
            )
            
            # Should skip unavailable Hatchet and select next available
            assert selected_backend == BackendType.TASK_ABSTRACTION

    @pytest.mark.asyncio
    async def test_user_segment_based_selection(self, backend_selector):
        """Test user segment-based backend selection."""
        
        user_segments = [
            {
                "segment": "premium_users",
                "users": ["premium_user_1", "premium_user_2"],
                "expected_backend": BackendType.HATCHET
            },
            {
                "segment": "standard_users", 
                "users": ["standard_user_1", "standard_user_2"],
                "expected_backend": BackendType.TASK_ABSTRACTION
            },
            {
                "segment": "free_users",
                "users": ["free_user_1", "free_user_2"],
                "expected_backend": BackendType.UNIFIED_CELERY
            }
        ]
        
        for segment in user_segments:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                def mock_segment_based_flags(flag_key, namespace, entity_id, context=None):
                    # Segment-based feature flag logic
                    if entity_id in segment["users"]:
                        if segment["segment"] == "premium_users":
                            return flag_key in ["task_abstraction_enabled", "hatchet_backend_enabled"]
                        elif segment["segment"] == "standard_users":
                            return flag_key == "task_abstraction_enabled"
                        elif segment["segment"] == "free_users":
                            return flag_key == "unified_celery_enabled"
                    return False
                
                mock_flag.side_effect = mock_segment_based_flags
                
                for user_id in segment["users"]:
                    selected_backend = await backend_selector.select_backend(
                        workflow_name="test_workflow",
                        user_context={"user_id": user_id, "organization_id": "test_org"}
                    )
                    
                    assert selected_backend == segment["expected_backend"], \
                        f"User {user_id} in {segment['segment']}: expected {segment['expected_backend']}, got {selected_backend}"

    @pytest.mark.asyncio
    async def test_workflow_specific_backend_preferences(self, backend_selector):
        """Test workflow-specific backend preferences."""
        
        workflow_preferences = [
            {
                "workflow_name": "cpu_intensive_workflow",
                "preferred_backend": BackendType.HATCHET,
                "feature_flags": {
                    "task_abstraction_enabled": True,
                    "hatchet_backend_enabled": True
                }
            },
            {
                "workflow_name": "io_intensive_workflow", 
                "preferred_backend": BackendType.TASK_ABSTRACTION,
                "feature_flags": {"task_abstraction_enabled": True}
            },
            {
                "workflow_name": "simple_workflow",
                "preferred_backend": BackendType.UNIFIED_CELERY,
                "feature_flags": {"unified_celery_enabled": True}
            }
        ]
        
        for preference in workflow_preferences:
            with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
                def mock_flag_response(flag_key, namespace, entity_id, context=None):
                    return preference["feature_flags"].get(flag_key, False)
                
                mock_flag.side_effect = mock_flag_response
                
                selected_backend = await backend_selector.select_backend(
                    workflow_name=preference["workflow_name"],
                    user_context={"user_id": "test_user", "organization_id": "test_org"}
                )
                
                assert selected_backend == preference["preferred_backend"], \
                    f"Workflow {preference['workflow_name']}: expected {preference['preferred_backend']}, got {selected_backend}"

    @pytest.mark.asyncio
    async def test_concurrent_backend_selection(self, backend_selector):
        """Test concurrent backend selection requests."""
        
        concurrent_requests = [
            {"user_id": f"user_{i}", "workflow": f"workflow_{i % 3}"}
            for i in range(20)
        ]
        
        with patch('unstract.flags.feature_flag.check_feature_flag_status') as mock_flag:
            # Mock consistent flag behavior
            def consistent_flag_behavior(flag_key, namespace, entity_id, context=None):
                # Deterministic based on user_id
                return hash(f"{flag_key}_{entity_id}") % 2 == 0
            
            mock_flag.side_effect = consistent_flag_behavior
            
            # Execute all selections concurrently
            tasks = [
                backend_selector.select_backend(
                    workflow_name=req["workflow"],
                    user_context={"user_id": req["user_id"], "organization_id": "test_org"}
                )
                for req in concurrent_requests
            ]
            
            results = await asyncio.gather(*tasks)
            
            # All requests should complete successfully
            assert len(results) == len(concurrent_requests)
            assert all(isinstance(result, BackendType) for result in results)
            
            # Same user should get consistent results
            user_backends = {}
            for i, result in enumerate(results):
                user_id = concurrent_requests[i]["user_id"]
                if user_id not in user_backends:
                    user_backends[user_id] = result
                else:
                    assert user_backends[user_id] == result, \
                        f"Inconsistent backend selection for user {user_id}"

    def test_backend_selector_interface_compliance(self):
        """Test that BackendSelector implements expected interface."""
        # This will fail initially - BackendSelector doesn't exist
        from unstract.task_abstraction.migration_manager import BackendSelector
        
        # Check required methods exist
        required_methods = [
            'select_backend', 'get_fallback_chain', 'check_backend_availability'
        ]
        
        for method_name in required_methods:
            assert hasattr(BackendSelector, method_name)
            assert callable(getattr(BackendSelector, method_name))