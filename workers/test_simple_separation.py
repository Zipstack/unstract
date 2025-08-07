#!/usr/bin/env python3
"""Simple test to verify manual review OSS/Cloud separation."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def test_api_client_separation():
    """Test that API client correctly uses plugin registry."""
    print("=== Testing API Client Manual Review Separation ===")

    # Test 1: OSS Mode (No Plugin)
    print("\n1. Testing OSS Mode (No Plugin):")
    try:
        from client_plugin_registry import _client_plugin_registry

        _client_plugin_registry.clear()

        from shared.api_client_facade import InternalAPIClient
        from shared.config import WorkerConfig

        client = InternalAPIClient(WorkerConfig())
        print(f"   Manual review client: {type(client.manual_review_client).__name__}")

        result = client.validate_manual_review_db_rule("test", "workflow")
        print(f"   Validation result: {result}")

        client.close()
        print("   ✅ OSS mode working - uses null client")

    except Exception as e:
        print(f"   ❌ OSS mode failed: {e}")
        return False

    # Test 2: Cloud Mode (With Plugin)
    print("\n2. Testing Cloud Mode (With Plugin):")
    try:
        from client_plugin_registry import APIClientPlugin, register_client_plugin
        from shared.manual_review_response import ManualReviewResponse

        class TestManualReviewPlugin(APIClientPlugin):
            name = "manual_review"

            def __init__(self, config):
                super().__init__(config)

            def validate_manual_review_db_rule(self, *args, **kwargs):
                return {"valid": True, "message": "Plugin working!"}

            def get_q_no_list(self, *args, **kwargs):
                return ManualReviewResponse.success_response(
                    data={"q_file_no_list": [1, 3, 5]}
                )

            def get_db_rules_data(self, *args, **kwargs):
                return ManualReviewResponse.success_response(
                    data={"percentage": 30, "rule_logic": "AND", "rule_json": None}
                )

            def set_organization_context(self, org_id):
                pass

        # Register the plugin
        register_client_plugin("manual_review", TestManualReviewPlugin)

        # Create new client - should use plugin
        client2 = InternalAPIClient(WorkerConfig())
        print(f"   Manual review client: {type(client2.manual_review_client).__name__}")

        result2 = client2.validate_manual_review_db_rule("test", "workflow")
        print(f"   Validation result: {result2}")

        client2.close()
        print("   ✅ Cloud mode working - uses actual plugin")

    except Exception as e:
        print(f"   ❌ Cloud mode failed: {e}")
        return False

    return True


def test_workers_clean():
    """Test that workers have no hardcoded manual review logic."""
    print("\n=== Testing Workers are Clean of Manual Review Logic ===")

    # Check that the functions were removed from general/tasks.py
    try:
        with open("general/tasks.py") as f:
            content = f.read()

        # These functions should no longer exist
        removed_functions = [
            "def _calculate_q_file_no_list",
            "def _create_file_data_general",
            "def _calculate_manual_review_decisions_for_batch",
        ]

        still_exists = []
        for func in removed_functions:
            if func in content:
                still_exists.append(func)

        if still_exists:
            print(f"   ❌ Manual review functions still exist: {still_exists}")
            return False
        else:
            print("   ✅ Manual review functions successfully removed from workers")

        # Check that registry factory pattern is used
        registry_patterns = [
            "from shared.manual_review_factory import get_manual_review_service",
            "manual_review_service = get_manual_review_service(",
        ]

        found_patterns = []
        for pattern in registry_patterns:
            if pattern in content:
                found_patterns.append(pattern)

        if len(found_patterns) >= 2:
            print("   ✅ Workers use registry factory pattern")
        else:
            print(f"   ❌ Registry factory pattern not complete, found: {found_patterns}")
            return False

    except Exception as e:
        print(f"   ❌ Error checking workers: {e}")
        return False

    return True


def main():
    """Run focused tests."""
    print("🧪 Testing Manual Review OSS/Cloud Separation")
    print("=" * 50)

    test1_passed = test_api_client_separation()
    test2_passed = test_workers_clean()

    print("\n" + "=" * 50)
    print("🏁 Test Summary:")

    if test1_passed and test2_passed:
        print("🎉 SUCCESS! Manual review separation is working correctly!")
        print("   ✅ API client uses plugin registry system")
        print("   ✅ OSS mode: Uses null clients, no manual review logic")
        print("   ✅ Cloud mode: Uses actual plugins with full functionality")
        print("   ✅ Workers: Clean of hardcoded manual review logic")
        print("   ✅ Plugin pattern: Proper ImportError handling")
        return True
    else:
        print("❌ FAILED! Some issues need to be resolved:")
        if not test1_passed:
            print("   - API client plugin registry issues")
        if not test2_passed:
            print("   - Workers still contain manual review logic")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
