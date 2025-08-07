#!/usr/bin/env python3
"""Simple test to verify the plugin system works correctly."""

import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))


def test_plugin_registry():
    """Test the plugin registry system."""
    print("Testing Plugin Registry System")
    print("=" * 40)

    try:
        from plugins import list_available_plugins

        print("✅ Plugin system imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import plugin system: {e}")
        return False

    # Test listing plugins
    try:
        plugins = list_available_plugins()
        print(f"✅ Found {len(plugins)} plugins")

        for plugin in plugins:
            print(f"   📦 {plugin['name']} - {plugin['path']}")

    except Exception as e:
        print(f"❌ Failed to list plugins: {e}")
        return False

    # Test plugin metadata
    if plugins:
        plugin_name = plugins[0]["name"]
        print(f"\n🔍 Testing plugin: {plugin_name}")

        # Check metadata
        has_components = []
        for component in [
            "has_client",
            "has_tasks",
            "has_dto",
            "has_backend_integration",
            "has_readme",
        ]:
            if plugins[0].get(component, False):
                has_components.append(component.replace("has_", ""))

        if has_components:
            print(f"✅ Plugin has components: {', '.join(has_components)}")
        else:
            print("⚠️  Plugin has no components")

    return True


def test_direct_imports():
    """Test direct imports of plugin components."""
    print("\nTesting Direct Plugin Component Imports")
    print("=" * 40)

    # Test DTO imports
    try:
        sys.path.insert(0, str(Path(__file__).parent / "plugins" / "manual_review"))

        from dto import QueueNames, ReviewDocument

        print("✅ DTO classes imported successfully")

        # Test DTO functionality
        _queue_names = QueueNames(
            review_q_name="test_queue",
            finished_review_q_name="test_finished",
            approved_queue_name="test_approved",
        )
        print("✅ QueueNames created successfully")

        doc = ReviewDocument(
            workflow_id="test-workflow",
            execution_id="test-execution",
            document_data={"test": "data"},
            organization_id="test-org",
        )
        _doc_dict = doc.to_dict()
        print("✅ ReviewDocument serialization works")

    except Exception as e:
        print(f"❌ DTO import/test failed: {e}")
        return False

    return True


def test_plugin_structure():
    """Test plugin directory structure."""
    print("\nTesting Plugin Structure")
    print("=" * 40)

    plugin_dir = Path(__file__).parent / "plugins" / "manual_review"

    expected_files = [
        "__init__.py",
        "client.py",
        "dto.py",
        "tasks.py",
        "README.md",
        "backend_integration.py",
        "test_plugin.py",
        "example_usage.py",
    ]

    all_present = True
    for filename in expected_files:
        filepath = plugin_dir / filename
        if filepath.exists():
            print(f"✅ {filename}")
        else:
            print(f"❌ {filename} - missing")
            all_present = False

    return all_present


def main():
    """Run all simple tests."""
    print("Manual Review Plugin - Simple Verification")
    print("=" * 50)

    tests = [
        test_plugin_registry,
        test_direct_imports,
        test_plugin_structure,
    ]

    passed = 0
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_func.__name__} failed")
        except Exception as e:
            print(f"❌ {test_func.__name__} error: {e}")

    print(f"\n{'=' * 50}")
    print(f"Simple Tests: {passed}/{len(tests)} passed")

    if passed == len(tests):
        print("🎉 All simple tests passed! Plugin system is working.")
        print("\n✅ Manual Review Plugin Status:")
        print("   - Plugin structure: Complete")
        print("   - Registry system: Working")
        print("   - Data structures: Functional")
        print("   - Ready for deployment")
    else:
        print("⚠️  Some tests failed. Check implementation.")

    return passed == len(tests)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
