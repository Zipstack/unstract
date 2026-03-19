#!/usr/bin/env python3
"""Check for updates to existing LLM and Embedding adapters.

This script analyzes current adapter JSON schemas and compares them
against known LiteLLM features to identify potential updates.

Usage:
    python check_adapter_updates.py
    python check_adapter_updates.py --adapter llm
    python check_adapter_updates.py --adapter embedding
    python check_adapter_updates.py --provider openai
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

# Known LiteLLM features by provider (update this periodically)
LITELLM_FEATURES = {
    "llm": {
        "openai": {
            "known_params": [
                "api_key",
                "api_base",
                "api_version",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "top_p",
                "n",
                "enable_reasoning",
                "reasoning_effort",
                "seed",
                "response_format",
                "tools",
                "tool_choice",
                "parallel_tool_calls",
                "logprobs",
            ],
            "reasoning_models": ["o1-mini", "o1-preview", "o3-mini", "o3", "o4-mini"],
            "latest_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-5"],
            "docs_url": "https://docs.litellm.ai/docs/providers/openai",
        },
        "anthropic": {
            "known_params": [
                "api_key",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "enable_thinking",
                "budget_tokens",
                "thinking",
            ],
            "thinking_models": ["claude-3-7-sonnet", "claude-sonnet-4", "claude-opus-4"],
            "latest_models": ["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805"],
            "docs_url": "https://docs.litellm.ai/docs/providers/anthropic",
        },
        "azure": {
            "known_params": [
                "api_key",
                "api_base",
                "api_version",
                "deployment_name",
                "azure_endpoint",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "enable_reasoning",
                "reasoning_effort",
            ],
            "reasoning_models": ["o1-mini", "o1-preview"],
            "docs_url": "https://docs.litellm.ai/docs/providers/azure",
        },
        "bedrock": {
            "known_params": [
                "aws_access_key_id",
                "aws_secret_access_key",
                "region_name",
                "aws_region_name",
                "aws_profile_name",
                "model_id",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "enable_thinking",
                "budget_tokens",
                "thinking",
                "top_k",
            ],
            "thinking_models": ["anthropic.claude-3-7-sonnet"],
            "docs_url": "https://docs.litellm.ai/docs/providers/bedrock",
        },
        "vertex_ai": {
            "known_params": [
                "json_credentials",
                "vertex_credentials",
                "project",
                "vertex_project",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "safety_settings",
                "enable_thinking",
                "budget_tokens",
                "thinking",
                "reasoning_effort",
                "tools",
                "googleSearch",
            ],
            "thinking_models": ["gemini-2.5-flash-preview", "gemini-2.5-pro"],
            "docs_url": "https://docs.litellm.ai/docs/providers/vertex",
        },
        "mistral": {
            "known_params": [
                "api_key",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "enable_reasoning",
                "reasoning_effort",
                "tools",
            ],
            "reasoning_models": ["magistral-medium-2506", "magistral-small-2506"],
            "latest_models": ["mistral-large-latest", "mistral-small-latest"],
            "docs_url": "https://docs.litellm.ai/docs/providers/mistral",
        },
        "ollama": {
            "known_params": [
                "base_url",
                "api_base",
                "model",
                "max_tokens",
                "temperature",
                "context_window",
                "request_timeout",
                "json_mode",
                "response_format",
                "tools",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/ollama",
        },
        "anyscale": {
            "known_params": [
                "api_key",
                "api_base",
                "model",
                "max_tokens",
                "max_retries",
                "timeout",
                "temperature",
                "additional_kwargs",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/anyscale",
        },
    },
    "embedding": {
        "openai": {
            "known_params": [
                "api_key",
                "api_base",
                "model",
                "embed_batch_size",
                "timeout",
                "dimensions",
            ],
            "latest_models": ["text-embedding-3-small", "text-embedding-3-large"],
            "docs_url": "https://docs.litellm.ai/docs/embedding/supported_embedding",
        },
        "azure": {
            "known_params": [
                "api_key",
                "api_base",
                "api_version",
                "deployment_name",
                "azure_endpoint",
                "model",
                "embed_batch_size",
                "timeout",
                "dimensions",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/azure",
        },
        "bedrock": {
            "known_params": [
                "aws_access_key_id",
                "aws_secret_access_key",
                "region_name",
                "aws_region_name",
                "model",
                "max_retries",
                "timeout",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/bedrock_embedding",
        },
        "vertexai": {
            "known_params": [
                "json_credentials",
                "vertex_credentials",
                "project",
                "vertex_project",
                "model",
                "embed_batch_size",
                "embed_mode",
                "dimensions",
                "input_type",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/vertex",
        },
        "ollama": {
            "known_params": [
                "base_url",
                "api_base",
                "model_name",
                "model",
                "embed_batch_size",
            ],
            "docs_url": "https://docs.litellm.ai/docs/providers/ollama",
        },
    },
}


def load_json_schema(adapter_type: str, provider: str) -> dict | None:
    """Load JSON schema for an adapter."""
    schema_dir = SDK1_ADAPTERS / f"{adapter_type}1" / "static"

    # Try common filename patterns
    for filename in [f"{provider}.json", f"{provider.replace('_', '')}.json"]:
        schema_path = schema_dir / filename
        if schema_path.exists():
            with open(schema_path) as f:
                return json.load(f)

    return None


def get_schema_properties(schema: dict) -> set[str]:
    """Extract property names from a JSON schema."""
    properties = set()

    if "properties" in schema:
        properties.update(schema["properties"].keys())

    # Check allOf conditional properties
    if "allOf" in schema:
        for item in schema["allOf"]:
            if "then" in item and "properties" in item["then"]:
                properties.update(item["then"]["properties"].keys())

    return properties


def analyze_adapter(adapter_type: str, provider: str) -> dict:
    """Analyze a single adapter for potential updates."""
    result = {
        "provider": provider,
        "adapter_type": adapter_type,
        "status": "ok",
        "current_properties": [],
        "missing_properties": [],
        "suggestions": [],
        "docs_url": None,
    }

    # Load schema
    schema = load_json_schema(adapter_type, provider)
    if not schema:
        result["status"] = "error"
        result["suggestions"].append(f"Schema not found for {provider}")
        return result

    # Get current properties
    current_props = get_schema_properties(schema)
    result["current_properties"] = sorted(current_props)

    # Get known LiteLLM features
    features = LITELLM_FEATURES.get(adapter_type, {}).get(provider, {})
    if not features:
        result["suggestions"].append(f"No LiteLLM feature data for {provider}")
        return result

    result["docs_url"] = features.get("docs_url")

    # Find missing parameters
    known_params = set(features.get("known_params", []))
    missing = (
        known_params - current_props - {"adapter_name"}
    )  # adapter_name is always present

    # Filter out params that might be named differently
    common_aliases = {
        "api_base": "base_url",
        "base_url": "api_base",
        "vertex_credentials": "json_credentials",
        "vertex_project": "project",
        "aws_region_name": "region_name",
    }

    filtered_missing = set()
    for param in missing:
        alias = common_aliases.get(param)
        if alias and alias in current_props:
            continue
        filtered_missing.add(param)

    result["missing_properties"] = sorted(filtered_missing)

    # Generate suggestions
    if filtered_missing:
        result["status"] = "needs_update"
        result["suggestions"].append(
            f"Consider adding: {', '.join(sorted(filtered_missing))}"
        )

    # Check for reasoning/thinking support
    if adapter_type == "llm":
        reasoning_models = features.get("reasoning_models", [])
        thinking_models = features.get("thinking_models", [])

        if (
            reasoning_models
            and "enable_reasoning" not in current_props
            and "reasoning_effort" not in current_props
        ):
            result["suggestions"].append(
                f"Consider adding reasoning support for models: {', '.join(reasoning_models)}"
            )

        if thinking_models and "enable_thinking" not in current_props:
            result["suggestions"].append(
                f"Consider adding thinking support for models: {', '.join(thinking_models)}"
            )

    # Check for model updates
    if "model" in schema.get("properties", {}):
        model_prop = schema["properties"]["model"]
        default_model = model_prop.get("default", "")
        latest_models = features.get("latest_models", [])

        if latest_models and default_model and default_model not in latest_models:
            result["suggestions"].append(
                f"Default model '{default_model}' may be outdated. Latest: {', '.join(latest_models[:3])}"
            )

    return result


def list_adapters(adapter_type: str) -> list[str]:
    """List all adapters of a given type."""
    adapter_dir = SDK1_ADAPTERS / f"{adapter_type}1"
    if not adapter_dir.exists():
        return []

    adapters = []
    for py_file in adapter_dir.glob("*.py"):
        if py_file.name.startswith("__"):
            continue
        adapters.append(py_file.stem)

    return adapters


def print_report(results: list[dict]) -> None:
    """Print analysis report."""
    print("\n" + "=" * 70)
    print("ADAPTER UPDATE CHECK REPORT")
    print("=" * 70)

    needs_update = [r for r in results if r["status"] == "needs_update"]
    ok = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]

    if needs_update:
        print(f"\n🟡 NEEDS UPDATE ({len(needs_update)}):")
        print("-" * 40)
        for r in needs_update:
            print(f"\n  {r['adapter_type'].upper()}: {r['provider']}")
            if r["missing_properties"]:
                print(f"    Missing: {', '.join(r['missing_properties'])}")
            for s in r["suggestions"]:
                print(f"    → {s}")
            if r["docs_url"]:
                print(f"    Docs: {r['docs_url']}")

    if ok:
        print(f"\n✅ UP TO DATE ({len(ok)}):")
        print("-" * 40)
        for r in ok:
            print(f"  {r['adapter_type'].upper()}: {r['provider']}")

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        print("-" * 40)
        for r in errors:
            print(f"  {r['adapter_type'].upper()}: {r['provider']}")
            for s in r["suggestions"]:
                print(f"    → {s}")

    print("\n" + "=" * 70)
    print(f"Total: {len(results)} adapters checked")
    print(f"  Needs update: {len(needs_update)}")
    print(f"  Up to date: {len(ok)}")
    print(f"  Errors: {len(errors)}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Check for updates to LLM and Embedding adapters"
    )
    parser.add_argument(
        "--adapter",
        choices=["llm", "embedding", "all"],
        default="all",
        help="Type of adapter to check",
    )
    parser.add_argument(
        "--provider", help="Specific provider to check (e.g., openai, anthropic)"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    print(f"SDK1 Adapters Path: {SDK1_ADAPTERS}")

    adapter_types = ["llm", "embedding"] if args.adapter == "all" else [args.adapter]
    results = []

    for adapter_type in adapter_types:
        if args.provider:
            providers = [args.provider]
        else:
            providers = list_adapters(adapter_type)

        for provider in providers:
            result = analyze_adapter(adapter_type, provider)
            results.append(result)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    # Return exit code based on results
    needs_update = any(r["status"] == "needs_update" for r in results)
    return 1 if needs_update else 0


if __name__ == "__main__":
    sys.exit(main())
