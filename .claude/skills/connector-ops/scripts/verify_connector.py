#!/usr/bin/env python3
"""
Verify a connector installation.

Usage:
    python verify_connector.py <connector_type> <connector_name>

Example:
    python verify_connector.py databases postgresql
    python verify_connector.py filesystems google_drive
    python verify_connector.py queues redis_queue

Checks:
1. Directory structure exists
2. Required files present
3. Metadata is valid
4. Connector can be imported
5. Connector is registered in Connectorkit
6. Syntax/compile check passes
7. Mock tests pass
"""

import sys
import os
import subprocess
import importlib
from pathlib import Path


def check_directory_structure(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Check required directory structure exists."""
    errors = []

    connector_dir = base_path / "src/unstract/connectors" / connector_type / connector_name

    if not connector_dir.exists():
        errors.append(f"Connector directory not found: {connector_dir}")
        return errors

    # Required files
    required_files = [
        "__init__.py",
        f"{connector_name}.py",
        "static/json_schema.json",
    ]

    for file in required_files:
        file_path = connector_dir / file
        if not file_path.exists():
            errors.append(f"Required file missing: {file_path}")

    return errors


def check_metadata(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Check metadata is valid."""
    errors = []

    # Add to path for import
    src_path = base_path / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    try:
        module_path = f"unstract.connectors.{connector_type}.{connector_name}"
        module = importlib.import_module(module_path)

        if not hasattr(module, "metadata"):
            errors.append("Module missing 'metadata' dict")
            return errors

        metadata = module.metadata

        # Required metadata fields
        required_fields = ["name", "version", "connector", "description", "is_active"]
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Metadata missing required field: {field}")

        if metadata.get("is_active") is not True:
            errors.append("Metadata 'is_active' is not True - connector won't be registered")

    except ImportError as e:
        errors.append(f"Failed to import connector module: {e}")

    return errors


def check_connector_class(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Check connector class is valid."""
    errors = []

    src_path = base_path / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    try:
        module_path = f"unstract.connectors.{connector_type}.{connector_name}"
        module = importlib.import_module(module_path)

        connector_class = module.metadata.get("connector")
        if connector_class is None:
            errors.append("Connector class not found in metadata")
            return errors

        # Check required static methods
        required_methods = [
            "get_id",
            "get_name",
            "get_description",
            "get_icon",
            "get_json_schema",
            "can_write",
            "can_read",
            "requires_oauth",
            "get_connector_mode",
        ]

        for method in required_methods:
            if not hasattr(connector_class, method):
                errors.append(f"Connector missing required method: {method}")
            else:
                # Try calling static methods
                try:
                    getattr(connector_class, method)()
                except Exception as e:
                    errors.append(f"Error calling {method}(): {e}")

    except Exception as e:
        errors.append(f"Error checking connector class: {e}")

    return errors


def check_connectorkit_registration(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Check connector is registered in Connectorkit."""
    errors = []

    src_path = base_path / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    try:
        from unstract.connectors.connectorkit import Connectorkit

        kit = Connectorkit()
        connectors = kit.get_connectors_list()

        # Get connector ID from module
        module_path = f"unstract.connectors.{connector_type}.{connector_name}"
        module = importlib.import_module(module_path)
        connector_class = module.metadata.get("connector")
        connector_id = connector_class.get_id()

        # Check if registered
        registered_ids = [c.get("id") for c in connectors]
        if connector_id not in registered_ids:
            errors.append(f"Connector not registered in Connectorkit. ID: {connector_id}")
        else:
            print(f"  Connector registered with ID: {connector_id}")

    except Exception as e:
        errors.append(f"Error checking Connectorkit registration: {e}")

    return errors


def run_syntax_check(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Run Python syntax/compile check."""
    errors = []

    connector_file = base_path / "src/unstract/connectors" / connector_type / connector_name / f"{connector_name}.py"

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(connector_file)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        errors.append(f"Syntax error: {result.stderr}")

    return errors


def run_mock_tests(base_path: Path, connector_type: str, connector_name: str) -> list[str]:
    """Run mock-based tests."""
    errors = []

    test_file = base_path / "tests" / connector_type / f"test_{connector_name}.py"

    if not test_file.exists():
        errors.append(f"Mock test file not found: {test_file}")
        return errors

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(base_path),
    )

    if result.returncode != 0:
        errors.append(f"Mock tests failed:\n{result.stdout}\n{result.stderr}")
    else:
        print(f"  Mock tests output:\n{result.stdout}")

    return errors


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_connector.py <connector_type> <connector_name>")
        print("Example: python verify_connector.py databases postgresql")
        sys.exit(1)

    connector_type = sys.argv[1]
    connector_name = sys.argv[2]

    # Validate connector type
    valid_types = ["databases", "filesystems", "queues"]
    if connector_type not in valid_types:
        print(f"Invalid connector type: {connector_type}")
        print(f"Must be one of: {valid_types}")
        sys.exit(1)

    # Find base path (unstract/connectors)
    script_dir = Path(__file__).parent
    base_path = script_dir.parent.parent.parent.parent / "unstract/connectors"

    if not base_path.exists():
        # Try relative to current working directory
        base_path = Path.cwd()
        if not (base_path / "src/unstract/connectors").exists():
            print(f"Could not find connectors base path")
            sys.exit(1)

    print(f"Verifying connector: {connector_type}/{connector_name}")
    print(f"Base path: {base_path}")
    print("=" * 60)

    all_errors = []

    # Run checks
    checks = [
        ("Directory Structure", check_directory_structure),
        ("Metadata Validation", check_metadata),
        ("Connector Class", check_connector_class),
        ("Connectorkit Registration", check_connectorkit_registration),
        ("Syntax Check", run_syntax_check),
        ("Mock Tests", run_mock_tests),
    ]

    for check_name, check_func in checks:
        print(f"\n[{check_name}]")
        errors = check_func(base_path, connector_type, connector_name)

        if errors:
            print(f"  FAILED:")
            for error in errors:
                print(f"    - {error}")
            all_errors.extend(errors)
        else:
            print(f"  PASSED")

    print("\n" + "=" * 60)

    if all_errors:
        print(f"VERIFICATION FAILED: {len(all_errors)} error(s) found")
        sys.exit(1)
    else:
        print("VERIFICATION PASSED: All checks successful")
        sys.exit(0)


if __name__ == "__main__":
    main()
