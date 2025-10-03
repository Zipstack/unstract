"""Plugin Manager for Workers

This module provides programmatic tools for managing worker plugins.
CLI functionality has been removed as plugins are managed programmatically.
"""

import json
import logging
import sys
from pathlib import Path

# Add the workers directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logger
logger = logging.getLogger(__name__)

try:
    from plugins import (
        get_plugin,
        get_plugin_requirements,
        list_available_plugins,
        validate_plugin_structure,
    )
except ImportError as e:
    logger.error(f"Error importing plugin system: {e}")
    logger.error("Make sure you're running this from the workers directory")
    sys.exit(1)


class PluginManager:
    """Plugin management operations."""

    def list_plugins(self) -> None:
        """List all available plugins."""
        plugins = list_available_plugins()

        if not plugins:
            logger.info("No plugins found in the plugins directory.")
            return

        logger.info(f"Found {len(plugins)} plugin(s):\n")

        for plugin in plugins:
            logger.info(f"📦 {plugin['name']}")
            logger.info(f"   Path: {plugin['path']}")

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
                logger.info(f"   Components: {', '.join(components)}")
            else:
                logger.info("   Components: none")

            logger.info("")

    def show_plugin_info(self, plugin_name: str) -> None:
        """Show detailed information about a plugin."""
        logger.info(f"Plugin Information: {plugin_name}")
        logger.info("=" * 50)

        self._show_plugin_metadata(plugin_name)
        self._show_plugin_structure_validation(plugin_name)
        self._show_plugin_loading_test(plugin_name)

    def _show_plugin_metadata(self, plugin_name: str) -> None:
        """Display plugin metadata information."""
        requirements = get_plugin_requirements(plugin_name)
        if not requirements:
            return

        logger.info("Metadata:")
        for key, value in requirements.items():
            if isinstance(value, (list, dict)):
                logger.info(f"  {key}: {json.dumps(value, indent=4)}")
            else:
                logger.info(f"  {key}: {value}")
        logger.info("")

    def _show_plugin_structure_validation(self, plugin_name: str) -> None:
        """Display plugin structure validation results."""
        validation = validate_plugin_structure(plugin_name)
        logger.info("Structure Validation:")
        for check, result in validation.items():
            status = "✅" if result else "❌"
            logger.info(f"  {status} {check}")
        logger.info("")

    def _show_plugin_loading_test(self, plugin_name: str) -> None:
        """Test and display plugin loading results."""
        logger.info("Plugin Loading Test:")
        try:
            plugin = get_plugin(plugin_name)
            if plugin:
                logger.info("  ✅ Plugin loaded successfully")
                self._show_plugin_type_info(plugin)
            else:
                logger.error("  ❌ Plugin failed to load")
        except Exception as e:
            logger.error(f"  ❌ Plugin loading error: {e}")
        logger.info("")

    def _show_plugin_type_info(self, plugin) -> None:
        """Display plugin type information."""
        if hasattr(plugin, "__name__"):
            logger.info(f"  📋 Plugin type: {plugin.__name__}")
        elif hasattr(plugin, "__class__"):
            logger.info(f"  📋 Plugin type: {plugin.__class__.__name__}")

    def validate_plugin(self, plugin_name: str) -> bool:
        """Validate a plugin thoroughly."""
        logger.info(f"Validating Plugin: {plugin_name}")
        logger.info("=" * 50)

        # Structure validation
        if not self._validate_plugin_structure(plugin_name):
            return False

        # Import test
        return self._validate_plugin_import(plugin_name)

    def _validate_plugin_structure(self, plugin_name: str) -> bool:
        """Validate plugin structure and return True if valid."""
        validation = validate_plugin_structure(plugin_name)
        structure_valid = True

        logger.info("Structure Validation:")
        for check, result in validation.items():
            status = "✅" if result else "❌"
            logger.info(f"  {status} {check}")
            if not result and check in ["exists", "has_init"]:
                structure_valid = False

        if not structure_valid:
            logger.error("\n❌ Plugin has critical structure issues")
            return False

        logger.info("")
        return True

    def _validate_plugin_import(self, plugin_name: str) -> bool:
        """Validate plugin import and methods."""
        logger.info("Import Test:")
        try:
            plugin = get_plugin(plugin_name)
            if not plugin:
                logger.error("  ❌ Plugin failed to import")
                return False

            logger.info("  ✅ Plugin imports successfully")
            self._test_plugin_methods(plugin)
            logger.info("\n✅ Plugin validation completed successfully")
            return True

        except Exception as e:
            logger.error(f"  ❌ Import error: {e}")
            return False

    def _test_plugin_methods(self, plugin) -> None:
        """Test plugin methods if available."""
        if hasattr(plugin, "get_metadata"):
            try:
                plugin.get_metadata()
                logger.info("  ✅ Plugin metadata accessible")
            except Exception as e:
                logger.warning(f"  ⚠️  Plugin metadata error: {e}")

        if hasattr(plugin, "validate_requirements"):
            try:
                plugin.validate_requirements()
                logger.info("  ✅ Plugin requirements validation available")
            except Exception as e:
                logger.warning(f"  ⚠️  Plugin requirements validation error: {e}")

    def test_plugin(self, plugin_name: str) -> None:
        """Run tests for a plugin."""
        logger.info(f"Testing Plugin: {plugin_name}")
        logger.info("=" * 50)

        plugin_path = Path(__file__).parent / plugin_name
        test_file = plugin_path / "test_plugin.py"

        if not test_file.exists():
            logger.error("❌ No test file found (test_plugin.py)")
            return

        logger.info("🧪 Running plugin tests...")

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
                logger.info("✅ Tests passed!")
                logger.info("\nTest Output:")
                logger.info(result.stdout)
            else:
                logger.error("❌ Tests failed!")
                logger.info("\nTest Output:")
                logger.info(result.stdout)
                if result.stderr:
                    logger.error("\nError Output:")
                    logger.error(result.stderr)

        except subprocess.TimeoutExpired:
            logger.warning("⏰ Tests timed out after 60 seconds")
        except Exception as e:
            logger.error(f"❌ Error running tests: {e}")

    def install_plugin_deps(self, plugin_name: str) -> None:
        """Install dependencies for a plugin."""
        logger.info(f"Installing Dependencies for Plugin: {plugin_name}")
        logger.info("=" * 50)

        requirements = get_plugin_requirements(plugin_name)

        if not requirements:
            logger.error("❌ No plugin requirements found")
            return

        dependencies = requirements.get("dependencies", [])

        if not dependencies:
            logger.info("ℹ️  No dependencies specified for this plugin")
            return

        logger.info("Dependencies to install:")
        for dep in dependencies:
            logger.info(f"  - {dep}")

        logger.info("\n🚀 Installing dependencies...")

        import subprocess

        try:
            # Install using pip
            cmd = [sys.executable, "-m", "pip", "install"] + dependencies
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("✅ Dependencies installed successfully!")
            else:
                logger.error("❌ Failed to install dependencies")
                logger.error("Error output:")
                logger.error(result.stderr)

        except Exception as e:
            logger.error(f"❌ Error installing dependencies: {e}")
