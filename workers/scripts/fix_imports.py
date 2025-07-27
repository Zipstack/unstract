#!/usr/bin/env python3
"""Fix import paths in worker files to remove Django dependencies."""

import re
from pathlib import Path


def fix_imports_in_file(file_path: Path):
    """Fix import paths in a single file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Fix backend.workers.shared imports
        content = re.sub(
            r"from backend\.workers\.shared import", "from shared import", content
        )

        content = re.sub(r"from backend\.workers\.shared\.", "from shared.", content)

        # Fix backend.workers.monitoring imports
        content = re.sub(
            r"from backend\.workers\.monitoring\.", "from monitoring.", content
        )

        # Fix backend.workers.config imports
        content = re.sub(r"from backend\.workers\.config\.", "from config.", content)

        # Fix celery app imports
        content = re.sub(r"celery -A backend\.workers\.(\w+)", r"celery -A \1", content)

        # Fix Docker CMD references
        content = re.sub(r"backend\.workers\.(\w+)", r"\1", content)

        # Only write if content changed
        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Fixed imports in: {file_path}")

    except Exception as e:
        print(f"Error processing {file_path}: {e}")


def main():
    """Fix imports in all worker files."""
    workers_dir = Path(__file__).parent.parent

    # Find all Python files in worker directories
    python_files = []
    for pattern in ["**/*.py", "**/*.Dockerfile", "**/*.yml", "**/*.yaml", "**/*.sh"]:
        python_files.extend(workers_dir.glob(pattern))

    print(f"Processing {len(python_files)} files...")

    for file_path in python_files:
        if file_path.name != "fix_imports.py":  # Skip this script
            fix_imports_in_file(file_path)

    print("Import fixing complete!")


if __name__ == "__main__":
    main()
