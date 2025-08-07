#!/usr/bin/env python3
"""Test the plugin registry approach without try/except ImportError."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def test_registry_factory():
    """Test the manual review factory with plugin registry."""
    print("=== Testing Plugin Registry Factory Approach ===")

    # Test 1: OSS Mode (No Plugin)
    print("\n1. Testing OSS Mode (No Plugin):")
    try:
        from client_plugin_registry import _client_plugin_registry

        _client_plugin_registry.clear()

        from shared.api_client_facade import InternalAPIClient
        from shared.config import WorkerConfig
        from shared.manual_review_factory import get_manual_review_service

        api_client = InternalAPIClient(WorkerConfig())
        service = get_manual_review_service(api_client, "test-org")

        print(f"   Service type: {type(service).__name__}")

        # Test service methods
        config = service.get_manual_review_config("test-workflow", 10)
        print(f"   Config review_required: {config.get('review_required')}")

        q_list = service.calculate_q_file_no_list(config, 10)
        print(f"   Q file list length: {len(q_list)}")

        batch = [("file1.pdf", {}), ("file2.pdf", {})]
        decisions = service.calculate_batch_decisions(batch, {}, config)
        print(f"   Batch decisions: {decisions}")

        api_client.close()
        print("   ✅ OSS mode working - uses null service via registry")

    except Exception as e:
        print(f"   ❌ OSS mode failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 2: Cloud Mode (With Plugin)
    print("\n2. Testing Cloud Mode (With Plugin):")
    try:
        from client_plugin_registry import APIClientPlugin, register_client_plugin
        from shared.manual_review_response import ManualReviewResponse

        class TestManualReviewClient(APIClientPlugin):
            name = "manual_review"

            def __init__(self, config):
                super().__init__(config)

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
        register_client_plugin("manual_review", TestManualReviewClient)

        # Create new service - should use plugin
        api_client2 = InternalAPIClient(WorkerConfig())
        service2 = get_manual_review_service(api_client2, "test-org")

        print(f"   Service type: {type(service2).__name__}")

        # Test service methods with plugin
        config2 = service2.get_manual_review_config("test-workflow", 10)
        print(f"   Config review_required: {config2.get('review_required')}")
        print(f"   Config percentage: {config2.get('review_percentage')}")

        q_list2 = service2.calculate_q_file_no_list(config2, 10)
        print(f"   Q file list: {q_list2}")

        batch2 = [
            ("file1.pdf", {}),
            ("file2.pdf", {}),
            ("file3.pdf", {}),
            ("file4.pdf", {}),
        ]
        decisions2 = service2.calculate_batch_decisions(batch2, {}, config2)
        print(f"   Batch decisions: {decisions2}")
        print(f"   Files selected for review: {sum(decisions2)}/{len(decisions2)}")

        api_client2.close()
        print("   ✅ Cloud mode working - uses plugin via registry")

    except Exception as e:
        print(f"   ❌ Cloud mode failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


def test_no_try_except():
    """Test that no try/except ImportError patterns remain."""
    print("\n=== Testing No Try/Except ImportError Patterns ===")

    try:
        # Check general/tasks.py for try/except ImportError patterns
        with open("general/tasks.py") as f:
            content = f.read()

        # These patterns should no longer exist
        bad_patterns = [
            "except ImportError:",
            "try:\n        from plugins.manual_review",
            "Plugin not available",
        ]

        found_patterns = []
        for pattern in bad_patterns:
            if pattern in content:
                found_patterns.append(pattern)

        if found_patterns:
            print(f"   ❌ Found try/except ImportError patterns: {found_patterns}")
            return False
        else:
            print("   ✅ No try/except ImportError patterns found")

        # Check that factory import pattern is used
        good_patterns = [
            "from shared.manual_review_factory import get_manual_review_service",
            "manual_review_service = get_manual_review_service(",
        ]

        found_good = []
        for pattern in good_patterns:
            if pattern in content:
                found_good.append(pattern)

        if len(found_good) >= 2:
            print("   ✅ Factory pattern correctly implemented")
        else:
            print("   ❌ Factory pattern not found")
            return False

    except Exception as e:
        print(f"   ❌ Error checking patterns: {e}")
        return False

    return True


def test_backward_compatibility():
    """Test that the API client still works as before."""
    print("\n=== Testing Backward Compatibility ===")

    try:
        # Clear plugins first
        from client_plugin_registry import _client_plugin_registry
        from shared.api_client_facade import InternalAPIClient
        from shared.config import WorkerConfig

        _client_plugin_registry.clear()

        # Test basic API client functionality
        client = InternalAPIClient(WorkerConfig())

        print(f"   Manual review client: {type(client.manual_review_client).__name__}")

        # Test manual review API methods still work
        result1 = client.validate_manual_review_db_rule("test", "workflow")
        print(f"   DB rule validation: {result1.get('valid', False)}")

        result2 = client.enqueue_manual_review("queue", {"test": "data"})
        print(f"   Enqueue success: {result2.get('success', False)}")

        client.close()
        print("   ✅ Backward compatibility maintained")
        return True

    except Exception as e:
        print(f"   ❌ Backward compatibility failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all registry approach tests."""
    print("🧪 Testing Plugin Registry Approach (No Try/Catch)")
    print("=" * 55)

    results = []
    results.append(test_registry_factory())
    results.append(test_no_try_except())
    results.append(test_backward_compatibility())

    print("\n" + "=" * 55)
    print("🏁 Test Results:")
    print(f"✅ Passed: {sum(results)}/{len(results)}")

    if all(results):
        print("🎉 SUCCESS! Registry approach working perfectly!")
        print("   ✅ No try/except ImportError patterns")
        print("   ✅ Clean plugin registry factory")
        print("   ✅ OSS mode: Uses null service automatically")
        print("   ✅ Cloud mode: Uses plugin service automatically")
        print("   ✅ Backward compatibility maintained")
        print("   ✅ Single import, no error handling needed")
    else:
        print("❌ FAILED! Registry approach needs fixes:")
        if not results[0]:
            print("   - Registry factory issues")
        if not results[1]:
            print("   - Try/except patterns still exist")
        if not results[2]:
            print("   - Backward compatibility broken")

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
