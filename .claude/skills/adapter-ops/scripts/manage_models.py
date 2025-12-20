#!/usr/bin/env python3
"""Manage models in existing adapter JSON schemas.

Usage:
    # Add models to dropdown enum
    python manage_models.py --adapter llm --provider openai --action add-enum --models "gpt-4-turbo,gpt-4o"

    # Remove models from dropdown enum
    python manage_models.py --adapter llm --provider openai --action remove-enum --models "gpt-3.5-turbo"

    # Set default model
    python manage_models.py --adapter llm --provider openai --action set-default --models "gpt-4o"

    # Update model description
    python manage_models.py --adapter llm --provider openai --action update-description \
        --description "Available models: gpt-4o, gpt-4-turbo, gpt-3.5-turbo"

    # List current models
    python manage_models.py --adapter llm --provider openai --action list
"""

import argparse
import json
import sys
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
SDK1_ADAPTERS = REPO_ROOT / "unstract" / "sdk1" / "src" / "unstract" / "sdk1" / "adapters"


def get_schema_path(adapter_type: str, provider: str) -> Path:
    """Get the JSON schema path for an adapter."""
    adapter_dir = "llm1" if adapter_type == "llm" else "embedding1"
    return SDK1_ADAPTERS / adapter_dir / "static" / f"{provider.lower()}.json"


def load_schema(schema_path: Path) -> dict:
    """Load and parse a JSON schema file."""
    with open(schema_path) as f:
        return json.load(f)


def save_schema(schema_path: Path, schema: dict) -> None:
    """Save a JSON schema file with proper formatting."""
    with open(schema_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")


def list_models(schema: dict) -> dict:
    """Extract model information from schema."""
    model_prop = schema.get("properties", {}).get("model", {})
    return {
        "type": model_prop.get("type", "unknown"),
        "default": model_prop.get("default"),
        "enum": model_prop.get("enum"),
        "description": model_prop.get("description"),
    }


def add_enum_models(schema: dict, models: list[str]) -> dict:
    """Add models to the enum list (creates enum if doesn't exist)."""
    if "properties" not in schema:
        schema["properties"] = {}
    if "model" not in schema["properties"]:
        schema["properties"]["model"] = {"type": "string", "title": "Model"}

    model_prop = schema["properties"]["model"]

    # Get existing enum or create new one
    existing_enum = model_prop.get("enum", [])
    if not isinstance(existing_enum, list):
        existing_enum = []

    # Add new models (avoiding duplicates)
    for model in models:
        if model not in existing_enum:
            existing_enum.append(model)

    model_prop["enum"] = existing_enum

    # Set default if not set
    if "default" not in model_prop and existing_enum:
        model_prop["default"] = existing_enum[0]

    return schema


def remove_enum_models(schema: dict, models: list[str]) -> dict:
    """Remove models from the enum list."""
    model_prop = schema.get("properties", {}).get("model", {})
    existing_enum = model_prop.get("enum", [])

    if not existing_enum:
        return schema

    # Remove specified models
    updated_enum = [m for m in existing_enum if m not in models]
    model_prop["enum"] = updated_enum

    # Update default if it was removed
    if model_prop.get("default") in models and updated_enum:
        model_prop["default"] = updated_enum[0]
    elif not updated_enum:
        # Remove enum entirely if no models left
        if "enum" in model_prop:
            del model_prop["enum"]

    return schema


def set_default_model(schema: dict, model: str) -> dict:
    """Set the default model."""
    if "properties" not in schema:
        schema["properties"] = {}
    if "model" not in schema["properties"]:
        schema["properties"]["model"] = {"type": "string", "title": "Model"}

    schema["properties"]["model"]["default"] = model
    return schema


def update_description(schema: dict, description: str) -> dict:
    """Update the model field description."""
    if "properties" not in schema:
        schema["properties"] = {}
    if "model" not in schema["properties"]:
        schema["properties"]["model"] = {"type": "string", "title": "Model"}

    schema["properties"]["model"]["description"] = description
    return schema


def convert_to_enum(schema: dict) -> dict:
    """Convert free-text model field to enum dropdown."""
    model_prop = schema.get("properties", {}).get("model", {})

    if "enum" in model_prop:
        print("Model field already has enum defined")
        return schema

    # Get current default or prompt for models
    current_default = model_prop.get("default", "")

    print(f"Current default: {current_default}")
    print("To convert to enum, use --action add-enum with --models")

    return schema


def convert_to_freetext(schema: dict) -> dict:
    """Convert enum dropdown to free-text model field."""
    model_prop = schema.get("properties", {}).get("model", {})

    if "enum" in model_prop:
        # Preserve default if it exists
        default = model_prop.get("default", model_prop["enum"][0] if model_prop["enum"] else "")
        del model_prop["enum"]
        model_prop["default"] = default

    return schema


def main():
    parser = argparse.ArgumentParser(
        description="Manage models in adapter JSON schemas"
    )
    parser.add_argument(
        "--adapter",
        required=True,
        choices=["llm", "embedding"],
        help="Adapter type (llm or embedding)"
    )
    parser.add_argument(
        "--provider",
        required=True,
        help="Provider name (e.g., 'openai', 'anthropic')"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["list", "add-enum", "remove-enum", "set-default", "update-description", "to-enum", "to-freetext"],
        help="Action to perform"
    )
    parser.add_argument(
        "--models",
        help="Comma-separated list of models (for add/remove/set-default)"
    )
    parser.add_argument(
        "--description",
        help="New description for model field"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them"
    )

    args = parser.parse_args()

    # Get schema path
    schema_path = get_schema_path(args.adapter, args.provider)

    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        return 1

    # Load schema
    schema = load_schema(schema_path)
    original_schema = json.dumps(schema, indent=2)

    # Perform action
    if args.action == "list":
        info = list_models(schema)
        print(f"Model configuration for {args.provider} {args.adapter}:")
        print(f"  Type: {info['type']}")
        print(f"  Default: {info['default']}")
        if info['enum']:
            print(f"  Enum values: {', '.join(info['enum'])}")
        else:
            print("  Enum: (free text)")
        if info['description']:
            print(f"  Description: {info['description']}")
        return 0

    elif args.action == "add-enum":
        if not args.models:
            print("Error: --models required for add-enum action")
            return 1
        models = [m.strip() for m in args.models.split(",")]
        schema = add_enum_models(schema, models)
        print(f"Added models: {', '.join(models)}")

    elif args.action == "remove-enum":
        if not args.models:
            print("Error: --models required for remove-enum action")
            return 1
        models = [m.strip() for m in args.models.split(",")]
        schema = remove_enum_models(schema, models)
        print(f"Removed models: {', '.join(models)}")

    elif args.action == "set-default":
        if not args.models:
            print("Error: --models required for set-default action (single model)")
            return 1
        model = args.models.split(",")[0].strip()
        schema = set_default_model(schema, model)
        print(f"Set default model: {model}")

    elif args.action == "update-description":
        if not args.description:
            print("Error: --description required for update-description action")
            return 1
        schema = update_description(schema, args.description)
        print(f"Updated description")

    elif args.action == "to-enum":
        schema = convert_to_enum(schema)

    elif args.action == "to-freetext":
        schema = convert_to_freetext(schema)
        print("Converted to free-text field")

    # Show diff if changes were made
    new_schema = json.dumps(schema, indent=2)
    if original_schema != new_schema:
        if args.dry_run:
            print("\n[DRY RUN] Would update schema:")
            print("-" * 40)
            print(new_schema)
            print("-" * 40)
        else:
            save_schema(schema_path, schema)
            print(f"\nUpdated: {schema_path}")
    else:
        print("\nNo changes made")

    return 0


if __name__ == "__main__":
    sys.exit(main())
