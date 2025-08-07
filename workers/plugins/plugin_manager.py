#!/usr/bin/env python3
"""Plugin Manager for Workers

This script provides command-line tools for managing worker plugins.

Usage:
    python plugin_manager.py list                    # List all plugins
    python plugin_manager.py info <plugin_name>      # Get plugin info
    python plugin_manager.py validate <plugin_name>  # Validate plugin
    python plugin_manager.py test <plugin_name>      # Test plugin
    python plugin_manager.py install <plugin_name>   # Install plugin deps
"""

import argparse
import json
import sys
from pathlib import Path

# Add the workers directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from plugins import (
        get_plugin,
        get_plugin_requirements,
        list_available_plugins,
        validate_plugin_structure,
    )
except ImportError as e:
    print(f"Error importing plugin system: {e}")
    print("Make sure you're running this from the workers directory")
    sys.exit(1)


class PluginManager:
    """Plugin management operations."""

    def list_plugins(self) -> None:
        """List all available plugins."""
        plugins = list_available_plugins()

        if not plugins:
            print("No plugins found in the plugins directory.")
            return

        print(f"Found {len(plugins)} plugin(s):\n")

        for plugin in plugins:
            print(f"📦 {plugin['name']}")
            print(f"   Path: {plugin['path']}")

            # Show available components
            components = []
            if plugin.get("has_client", False):
                components.append("client")
            if plugin.get("has_tasks", False):
                components.append("tasks")
            if plugin.get("has_dto", False):
                components.append("dto")
            if plugin.get("has_backend_integration", False):
                components.append("backend-integration")
            if plugin.get("has_readme", False):
                components.append("readme")

            if components:
                print(f"   Components: {', '.join(components)}")
            else:
                print("   Components: none")

            print("")

    def show_plugin_info(self, plugin_name: str) -> None:
        """Show detailed information about a plugin."""
        print(f"Plugin Information: {plugin_name}")
        print("=" * 50)

        # Get plugin requirements/metadata
        requirements = get_plugin_requirements(plugin_name)
        if requirements:
            print("Metadata:")
            for key, value in requirements.items():
                if isinstance(value, (list, dict)):
                    print(f"  {key}: {json.dumps(value, indent=4)}")
                else:
                    print(f"  {key}: {value}")
            print("")

        # Validate plugin structure
        validation = validate_plugin_structure(plugin_name)
        print("Structure Validation:")
        for check, result in validation.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check}")
        print("")

        # Try to load the plugin
        print("Plugin Loading Test:")
        try:
            plugin = get_plugin(plugin_name)
            if plugin:
                print("  ✅ Plugin loaded successfully")
                if hasattr(plugin, "__name__"):
                    print(f"  📋 Plugin type: {plugin.__name__}")
                elif hasattr(plugin, "__class__"):
                    print(f"  📋 Plugin type: {plugin.__class__.__name__}")
            else:
                print("  ❌ Plugin failed to load")
        except Exception as e:
            print(f"  ❌ Plugin loading error: {e}")
        print("")

    def validate_plugin(self, plugin_name: str) -> bool:
        """Validate a plugin thoroughly."""
        print(f"Validating Plugin: {plugin_name}")
        print("=" * 50)

        # Structure validation
        validation = validate_plugin_structure(plugin_name)
        structure_valid = True

        print("Structure Validation:")
        for check, result in validation.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check}")
            if not result and check in ["exists", "has_init"]:
                structure_valid = False

        if not structure_valid:
            print("\n❌ Plugin has critical structure issues")
            return False

        print("")

        # Import test
        print("Import Test:")
        try:
            plugin = get_plugin(plugin_name)
            if plugin:
                print("  ✅ Plugin imports successfully")

                # Test plugin methods if it's a plugin class
                if hasattr(plugin, "get_metadata"):
                    try:
                        plugin.get_metadata()
                        print("  ✅ Plugin metadata accessible")
                    except Exception as e:
                        print(f"  ⚠️  Plugin metadata error: {e}")

                if hasattr(plugin, "validate_requirements"):
                    try:
                        plugin.validate_requirements()
                        print("  ✅ Plugin requirements validation available")
                    except Exception as e:
                        print(f"  ⚠️  Plugin requirements validation error: {e}")

            else:
                print("  ❌ Plugin failed to import")
                return False

        except Exception as e:
            print(f"  ❌ Import error: {e}")
            return False

        print("\n✅ Plugin validation completed successfully")
        return True

    def test_plugin(self, plugin_name: str) -> None:
        """Run tests for a plugin."""
        print(f"Testing Plugin: {plugin_name}")
        print("=" * 50)

        plugin_path = Path(__file__).parent / plugin_name
        test_file = plugin_path / "test_plugin.py"

        if not test_file.exists():
            print("❌ No test file found (test_plugin.py)")
            return

        print("🧪 Running plugin tests...")

        # Try to run the test file
        import os
        import subprocess

        try:
            # Set up environment
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).parent.parent)

            # Run the test
            result = subprocess.run(
                [sys.executable, str(test_file)],
                cwd=str(Path(__file__).parent.parent),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                print("✅ Tests passed!")
                print("\nTest Output:")
                print(result.stdout)
            else:
                print("❌ Tests failed!")
                print("\nTest Output:")
                print(result.stdout)
                if result.stderr:
                    print("\nError Output:")
                    print(result.stderr)

        except subprocess.TimeoutExpired:
            print("⏰ Tests timed out after 60 seconds")
        except Exception as e:
            print(f"❌ Error running tests: {e}")

    def install_plugin_deps(self, plugin_name: str) -> None:
        """Install dependencies for a plugin."""
        print(f"Installing Dependencies for Plugin: {plugin_name}")
        print("=" * 50)

        requirements = get_plugin_requirements(plugin_name)

        if not requirements:
            print("❌ No plugin requirements found")
            return

        dependencies = requirements.get("dependencies", [])

        if not dependencies:
            print("ℹ️  No dependencies specified for this plugin")
            return

        print("Dependencies to install:")
        for dep in dependencies:
            print(f"  - {dep}")

        print("\n🚀 Installing dependencies...")

        import subprocess

        try:
            # Install using pip
            cmd = [sys.executable, "-m", "pip", "install"] + dependencies
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print("✅ Dependencies installed successfully!")
            else:
                print("❌ Failed to install dependencies")
                print("Error output:")
                print(result.stderr)

        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Worker Plugin Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python plugin_manager.py list
  python plugin_manager.py info manual_review
  python plugin_manager.py validate manual_review
  python plugin_manager.py test manual_review
  python plugin_manager.py install manual_review
        """,
    )

    parser.add_argument(
        "command",
        choices=["list", "info", "validate", "test", "install"],
        help="Command to execute",
    )

    parser.add_argument(
        "plugin_name",
        nargs="?",
        help="Plugin name (required for info, validate, test, install)",
    )

    args = parser.parse_args()

    # Commands that don't require plugin_name
    if args.command == "list":
        manager = PluginManager()
        manager.list_plugins()
        return

    # Commands that require plugin_name
    if not args.plugin_name:
        print(f"Error: {args.command} command requires a plugin name")
        parser.print_help()
        sys.exit(1)

    manager = PluginManager()

    if args.command == "info":
        manager.show_plugin_info(args.plugin_name)
    elif args.command == "validate":
        success = manager.validate_plugin(args.plugin_name)
        sys.exit(0 if success else 1)
    elif args.command == "test":
        manager.test_plugin(args.plugin_name)
    elif args.command == "install":
        manager.install_plugin_deps(args.plugin_name)


if __name__ == "__main__":
    main()
