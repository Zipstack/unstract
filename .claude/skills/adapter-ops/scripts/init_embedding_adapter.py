#!/usr/bin/env python3
"""Initialize a new Embedding adapter for unstract/sdk1.

Usage:
    python init_embedding_adapter.py --provider newprovider --name "New Provider" --description "Description"
    python init_embedding_adapter.py --provider newprovider --name "New Provider" --description "Description" --logo-url "https://example.com/logo.png"
    python init_embedding_adapter.py --provider newprovider --name "New Provider" --description "Description" --auto-logo

This script creates:
    1. Adapter Python file in embedding1/{provider}.py
    2. JSON schema in embedding1/static/{provider}.json
    3. Optionally adds parameter class stub to base1.py
    4. Optionally downloads and adds provider logo (from URL or auto-detected)
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
# Find the sdk1 adapters directory relative to the repo root
REPO_ROOT = (
    SKILL_DIR.parent.parent.parent
)  # .claude/skills/unstract-adapter-extension -> repo root
SDK1_ADAPTERS = REPO_ROOT / "unstract" / "sdk1" / "src" / "unstract" / "sdk1" / "adapters"
ICONS_DIR = REPO_ROOT / "frontend" / "public" / "icons" / "adapter-icons"

EMBEDDING_ADAPTER_TEMPLATE = """from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, {param_class}
from unstract.sdk1.adapters.enums import AdapterTypes


class {class_name}({param_class}, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "{provider}|{uuid}"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {{
            "name": "{display_name}",
            "version": "1.0.0",
            "adapter": {class_name},
            "description": "{description}",
            "is_active": True,
        }}

    @staticmethod
    def get_name() -> str:
        return "{display_name}"

    @staticmethod
    def get_description() -> str:
        return "{description}"

    @staticmethod
    def get_provider() -> str:
        return "{provider}"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/{icon_name}.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
"""

EMBEDDING_SCHEMA_TEMPLATE = {
    "title": "{display_name} Embedding",
    "type": "object",
    "required": ["adapter_name", "api_key"],
    "properties": {
        "adapter_name": {
            "type": "string",
            "title": "Name",
            "default": "",
            "description": "Provide a unique name for this adapter instance. Example: {provider}-emb-1",
        },
        "model": {
            "type": "string",
            "title": "Model",
            "default": "",
            "description": "Provide the name of the embedding model.",
        },
        "api_key": {
            "type": "string",
            "title": "API Key",
            "default": "",
            "format": "password",
            "description": "Your {display_name} API key.",
        },
        "api_base": {
            "type": "string",
            "title": "API Base",
            "format": "uri",
            "default": "",
            "description": "API endpoint URL (if different from default).",
        },
        "embed_batch_size": {
            "type": "number",
            "minimum": 1,
            "multipleOf": 1,
            "title": "Embed Batch Size",
            "default": 10,
            "description": "Number of texts to embed in each batch.",
        },
        "timeout": {
            "type": "number",
            "minimum": 0,
            "multipleOf": 1,
            "title": "Timeout",
            "default": 240,
            "description": "Timeout in seconds",
        },
    },
}

PARAMETER_CLASS_TEMPLATE = '''
class {param_class}(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/{provider}."""

    api_key: str
    api_base: str | None = None
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = {param_class}.validate_model(adapter_metadata)
        return {param_class}(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model

'''


def to_class_name(provider: str) -> str:
    """Convert provider name to class name format."""
    special_cases = {
        "openai": "OpenAI",
        "azure_openai": "AzureOpenAI",
        "azure_ai_foundry": "AzureAIFoundry",
        "azure_ai": "AzureAI",
        "vertexai": "VertexAI",
        "aws_bedrock": "AWSBedrock",
        "bedrock": "AWSBedrock",
    }
    if provider.lower() in special_cases:
        return special_cases[provider.lower()]

    return "".join(
        word.capitalize() for word in provider.replace("_", " ").replace("-", " ").split()
    )


def to_icon_name(display_name: str) -> str:
    """Convert display name to icon filename (without extension)."""
    return display_name.replace(" ", "")


def fetch_url(url: str, timeout: int = 10) -> bytes | None:
    """Fetch content from URL with error handling."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        request = Request(url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (URLError, HTTPError, TimeoutError):
        return None


def search_potential_logo_sources(provider: str, display_name: str) -> list[dict]:
    """Search for potential logo sources for the given provider.

    This function only SEARCHES for potential sources and returns them.
    It does NOT verify if the logos are correct - that's up to the user.

    Returns:
        List of dicts with 'url' and 'source' keys for potential logos found
    """
    found_sources = []
    provider_lower = provider.lower().replace("_", "").replace("-", "")
    name_lower = display_name.lower().replace(" ", "")

    # Try Clearbit Logo API with common domain patterns
    domains = [
        (f"{provider_lower}.com", "company domain"),
        (f"{provider_lower}.ai", "AI domain"),
        (f"{name_lower}.com", "name domain"),
        (f"{name_lower}.ai", "name AI domain"),
    ]

    for domain, source_type in domains:
        url = f"https://logo.clearbit.com/{domain}"
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            request = Request(url, headers=headers, method="HEAD")
            with urlopen(request, timeout=5) as response:
                if response.status == 200:
                    found_sources.append(
                        {"url": url, "source": f"Clearbit ({source_type}: {domain})"}
                    )
        except (URLError, HTTPError, TimeoutError):
            continue

    # Try GitHub organization avatars
    github_names = [
        provider_lower,
        name_lower,
        provider.lower().replace("_", "-"),
    ]

    for name in github_names:
        url = f"https://github.com/{name}.png?size=512"
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            request = Request(url, headers=headers, method="HEAD")
            with urlopen(request, timeout=5) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "image" in content_type:
                        found_sources.append(
                            {"url": url, "source": f"GitHub avatar (@{name})"}
                        )
        except (URLError, HTTPError, TimeoutError):
            continue

    return found_sources


def download_and_process_logo(
    url: str, output_path: Path, target_size: int = 512
) -> bool:
    """Download logo from URL and process to standard format.

    Args:
        url: URL to download the logo from
        output_path: Path to save the logo
        target_size: Target size for square logo (default 512x512)

    Returns:
        True if successful, False otherwise

    Image settings: 4800 DPI density, 8-bit depth, 512x512 pixels
    """
    image_data = fetch_url(url, timeout=30)
    if not image_data:
        return False

    # Check if SVG (by URL extension or content)
    is_svg = (
        url.lower().endswith(".svg")
        or image_data[:5] == b"<?xml"
        or b"<svg" in image_data[:1000]
    )

    if is_svg:
        # Use ImageMagick for SVG conversion with optimal settings
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
            tmp.write(image_data)
            tmp_path = tmp.name

        try:
            # Convert SVG to PNG: 4800 DPI, 8-bit depth, 512x512
            result = subprocess.run(
                [
                    "magick",
                    "-density",
                    "4800",
                    "-background",
                    "none",
                    tmp_path,
                    "-resize",
                    f"{target_size}x{target_size}",
                    "-depth",
                    "8",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"  ImageMagick error: {result.stderr}")
                return False
            return True
        except FileNotFoundError:
            print(
                "  Note: ImageMagick not found. Install with: sudo pacman -S imagemagick"
            )
            return False
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # Handle raster images (PNG, JPG, etc.) with PIL
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image_data))

        if img.mode != "RGBA":
            img = img.convert("RGBA")

        if img.width != target_size or img.height != target_size:
            ratio = min(target_size / img.width, target_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            canvas = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 0))
            offset = ((target_size - img.width) // 2, (target_size - img.height) // 2)
            canvas.paste(img, offset, img if img.mode == "RGBA" else None)
            img = canvas

        img.save(output_path, "PNG")
        return True

    except ImportError:
        if image_data[:8] == b"\x89PNG\r\n\x1a\n":
            output_path.write_bytes(image_data)
            return True
        print("  Note: Install Pillow for better image processing: pip install Pillow")
        return False
    except Exception as e:
        print(f"  Error processing image: {e}")
        return False


def copy_logo(source_path: Path, output_path: Path, target_size: int = 512) -> bool:
    """Copy and optionally resize a local logo file.

    Image settings: 4800 DPI density, 8-bit depth, 512x512 pixels
    """
    if not source_path.exists():
        return False

    # Check if SVG
    is_svg = source_path.suffix.lower() == ".svg"

    if is_svg:
        # Use ImageMagick for SVG conversion with optimal settings
        import subprocess

        try:
            result = subprocess.run(
                [
                    "magick",
                    "-density",
                    "4800",
                    "-background",
                    "none",
                    str(source_path),
                    "-resize",
                    f"{target_size}x{target_size}",
                    "-depth",
                    "8",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"  ImageMagick error: {result.stderr}")
                return False
            return True
        except FileNotFoundError:
            print(
                "  Note: ImageMagick not found. Install with: sudo pacman -S imagemagick"
            )
            return False

    # Handle raster images with PIL
    try:
        from PIL import Image

        img = Image.open(source_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        if img.width != target_size or img.height != target_size:
            ratio = min(target_size / img.width, target_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            canvas = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 0))
            offset = ((target_size - img.width) // 2, (target_size - img.height) // 2)
            canvas.paste(img, offset, img if img.mode == "RGBA" else None)
            img = canvas

        img.save(output_path, "PNG")
        return True

    except ImportError:
        import shutil

        shutil.copy2(source_path, output_path)
        return True
    except Exception:
        return False


def create_embedding_adapter(
    provider: str,
    display_name: str,
    description: str,
    add_param_class: bool = False,
    use_existing_param_class: str | None = None,
    logo_url: str | None = None,
    logo_file: str | None = None,
    auto_logo: bool = False,
) -> dict:
    """Create a new Embedding adapter.

    Returns:
        dict with 'files_created' list and 'param_class_stub' if applicable
    """
    result = {"files_created": [], "param_class_stub": None, "errors": [], "warnings": []}

    if not SDK1_ADAPTERS.exists():
        result["errors"].append(f"SDK1 adapters directory not found at: {SDK1_ADAPTERS}")
        return result

    embedding_dir = SDK1_ADAPTERS / "embedding1"
    static_dir = embedding_dir / "static"

    if not embedding_dir.exists():
        result["errors"].append(
            f"Embedding adapters directory not found at: {embedding_dir}"
        )
        return result

    static_dir.mkdir(exist_ok=True)

    class_base = to_class_name(provider)
    class_name = f"{class_base}EmbeddingAdapter"
    icon_name = to_icon_name(display_name)
    adapter_uuid = str(uuid.uuid4())

    if use_existing_param_class:
        param_class = use_existing_param_class
    elif add_param_class:
        param_class = f"{class_base}EmbeddingParameters"
    else:
        param_class = "OpenAIEmbeddingParameters"

    adapter_content = EMBEDDING_ADAPTER_TEMPLATE.format(
        class_name=class_name,
        param_class=param_class,
        provider=provider.lower(),
        uuid=adapter_uuid,
        display_name=display_name,
        description=description,
        icon_name=icon_name,
    )

    adapter_file = embedding_dir / f"{provider.lower()}.py"
    if adapter_file.exists():
        result["errors"].append(f"Adapter file already exists: {adapter_file}")
    else:
        adapter_file.write_text(adapter_content)
        result["files_created"].append(str(adapter_file))

    schema = json.loads(json.dumps(EMBEDDING_SCHEMA_TEMPLATE))
    schema["title"] = f"{display_name} Embedding"
    schema["properties"]["adapter_name"]["description"] = (
        f"Provide a unique name for this adapter instance. Example: {provider.lower()}-emb-1"
    )
    schema["properties"]["api_key"]["description"] = f"Your {display_name} API key."

    schema_file = static_dir / f"{provider.lower()}.json"
    if schema_file.exists():
        result["errors"].append(f"Schema file already exists: {schema_file}")
    else:
        schema_file.write_text(json.dumps(schema, indent=2) + "\n")
        result["files_created"].append(str(schema_file))

    # Handle logo
    logo_path = ICONS_DIR / f"{icon_name}.png"
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    if logo_path.exists():
        result["warnings"].append(f"Logo already exists: {logo_path}")
    elif logo_url:
        # User provided explicit URL - download it
        if download_and_process_logo(logo_url, logo_path):
            result["files_created"].append(str(logo_path))
        else:
            result["warnings"].append(f"Failed to download logo from: {logo_url}")
    elif logo_file:
        # User provided local file - copy it
        if copy_logo(Path(logo_file), logo_path):
            result["files_created"].append(str(logo_path))
        else:
            result["warnings"].append(f"Failed to copy logo from: {logo_file}")
    elif auto_logo:
        # Search for potential sources but DO NOT auto-download
        # Just inform the user about what was found
        print(f"  Searching for potential logo sources for '{display_name}'...")
        potential_sources = search_potential_logo_sources(provider, display_name)
        if potential_sources:
            result["logo_suggestions"] = potential_sources
        else:
            result["warnings"].append(
                f"Could not find logo for '{display_name}'. "
                f"Please add manually to: {logo_path}"
            )

    if add_param_class:
        result["param_class_stub"] = PARAMETER_CLASS_TEMPLATE.format(
            param_class=param_class,
            provider=provider.lower(),
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a new Embedding adapter for unstract/sdk1"
    )
    parser.add_argument(
        "--provider",
        required=True,
        help="Provider identifier (lowercase, e.g., 'newprovider')",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Display name for the provider (e.g., 'New Provider')",
    )
    parser.add_argument("--description", required=True, help="Description of the adapter")
    parser.add_argument(
        "--add-param-class",
        action="store_true",
        help="Generate a parameter class stub for base1.py",
    )
    parser.add_argument(
        "--use-param-class",
        help="Use an existing parameter class (e.g., 'OpenAIEmbeddingParameters')",
    )
    parser.add_argument("--logo-url", help="URL to download the provider logo from")
    parser.add_argument("--logo-file", help="Path to a local logo file to copy")
    parser.add_argument(
        "--auto-logo",
        action="store_true",
        help="Automatically search for and download provider logo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating files",
    )

    args = parser.parse_args()

    icon_name = to_icon_name(args.name)

    print(f"Creating Embedding adapter for: {args.name}")
    print(f"Provider: {args.provider}")
    print(f"SDK1 Path: {SDK1_ADAPTERS}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would create:")
        print(f"  - {SDK1_ADAPTERS}/embedding1/{args.provider.lower()}.py")
        print(f"  - {SDK1_ADAPTERS}/embedding1/static/{args.provider.lower()}.json")
        if args.logo_url or args.logo_file or args.auto_logo:
            print(f"  - {ICONS_DIR}/{icon_name}.png (if logo found)")
        if args.add_param_class:
            print("  - Parameter class stub for base1.py")
        return 0

    result = create_embedding_adapter(
        provider=args.provider,
        display_name=args.name,
        description=args.description,
        add_param_class=args.add_param_class,
        use_existing_param_class=args.use_param_class,
        logo_url=args.logo_url,
        logo_file=args.logo_file,
        auto_logo=args.auto_logo,
    )

    if result["errors"]:
        print("Errors:")
        for error in result["errors"]:
            print(f"  - {error}")
        return 1

    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print("Files created:")
    for file in result["files_created"]:
        print(f"  - {file}")

    # Show logo suggestions if any were found
    if result.get("logo_suggestions"):
        print("\nPotential logo sources found (please verify before using):")
        for i, suggestion in enumerate(result["logo_suggestions"], 1):
            print(f"  {i}. {suggestion['source']}")
            print(f"     URL: {suggestion['url']}")
        print("\nTo use a logo, re-run with: --logo-url <URL>")
        print(f"Logo will be saved to: {ICONS_DIR}/{icon_name}.png")

    if result["param_class_stub"]:
        print("\nParameter class stub (add to base1.py):")
        print("-" * 60)
        print(result["param_class_stub"])
        print("-" * 60)

    print("\nNext steps:")
    print("1. Customize the JSON schema in static/{provider}.json")
    print("2. If needed, add parameter class to base1.py")
    print("3. Update the adapter to use the correct parameter class")
    if not any("png" in f for f in result["files_created"]) and not result.get(
        "logo_suggestions"
    ):
        print(f"4. Add logo manually to: {ICONS_DIR}/{icon_name}.png")
    print("5. Test with: from unstract.sdk1.adapters.adapterkit import Adapterkit")

    return 0


if __name__ == "__main__":
    sys.exit(main())
