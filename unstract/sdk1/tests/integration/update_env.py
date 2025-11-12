#!/usr/bin/env python3
"""Smart .env.test updater that merges .env.test.sample with existing .env.test.

This script:
1. Preserves all existing values in .env.test
2. Adds new variables from .env.test.sample
3. Updates comments from .env.test.sample
4. Maintains the structure and organization from .env.test.sample
5. Creates a backup of .env.test before updating

Usage:
    python update_env.py
    # Or make executable: chmod +x update_env.py && ./update_env.py
"""

import shutil
from datetime import datetime
from pathlib import Path


def parse_env_file(filepath: Path) -> dict[str, str]:
    """Parse .env file and extract key-value pairs.

    Args:
        filepath: Path to .env file

    Returns:
        Dictionary mapping environment variable names to their values
    """
    env_vars = {}
    if not filepath.exists():
        return env_vars

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse key=value
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value

    return env_vars


def merge_env_files(
    sample_file: Path, existing_file: Path, output_file: Path
) -> tuple[int, int, int]:
    """Merge .env.test.sample with existing .env.test.

    Args:
        sample_file: Path to .env.test.sample (template)
        existing_file: Path to existing .env.test (current values)
        output_file: Path to write merged output

    Returns:
        Tuple of (preserved_count, added_count, updated_count)
    """
    # Parse existing values
    existing_values = parse_env_file(existing_file)

    # Track statistics
    preserved_count = 0
    added_count = 0
    updated_count = 0

    # Read sample file and process line by line
    merged_lines = []
    with open(sample_file, encoding="utf-8") as f:
        for line in f:
            original_line = line.rstrip()

            # Keep comments and empty lines as-is from sample
            if not original_line or original_line.strip().startswith("#"):
                merged_lines.append(original_line)
                continue

            # Parse environment variable line
            if "=" in original_line:
                key = original_line.split("=", 1)[0].strip()

                # Check if we have an existing value for this key
                if key in existing_values:
                    # Preserve existing value
                    existing_value = existing_values[key]
                    # Extract the comment part if it exists (from the sample line, not the value part)
                    # Split on first # that's NOT inside quotes
                    parts = original_line.split("=", 1)
                    if len(parts) == 2:
                        value_and_comment = parts[1]
                        # Find comment after the value (not inside quotes)
                        # Simple approach: find # after closing quote
                        if '"' in value_and_comment:
                            # Has quoted value
                            first_quote = value_and_comment.find('"')
                            after_first_quote = value_and_comment[first_quote + 1 :]
                            if '"' in after_first_quote:
                                closing_quote_pos = after_first_quote.find('"')
                                after_closing_quote = after_first_quote[
                                    closing_quote_pos + 1 :
                                ]
                                if "#" in after_closing_quote:
                                    comment_part = after_closing_quote.split("#", 1)[
                                        1
                                    ].strip()
                                    merged_line = (
                                        f'{key}="{existing_value}"  # {comment_part}'
                                    )
                                else:
                                    merged_line = f'{key}="{existing_value}"'
                            else:
                                merged_line = f'{key}="{existing_value}"'
                        elif "#" in value_and_comment:
                            # No quotes, simple comment
                            comment_part = value_and_comment.split("#", 1)[1].strip()
                            merged_line = f'{key}="{existing_value}"  # {comment_part}'
                        else:
                            merged_line = f'{key}="{existing_value}"'
                    else:
                        merged_line = f'{key}="{existing_value}"'

                    merged_lines.append(merged_line)
                    preserved_count += 1
                else:
                    # New variable from sample - add it
                    merged_lines.append(original_line)
                    added_count += 1
            else:
                # Keep any other lines as-is
                merged_lines.append(original_line)

    # Write merged output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(merged_lines))
        f.write("\n")  # Ensure trailing newline

    return preserved_count, added_count, updated_count


def main():
    """Main execution function."""
    # Setup paths
    script_dir = Path(__file__).parent
    sample_file = script_dir / ".env.test.sample"
    existing_file = script_dir / ".env.test"
    backup_file = (
        script_dir / f".env.test.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    print("🔄 Smart .env.test Updater")
    print("=" * 60)

    # Validate sample file exists
    if not sample_file.exists():
        print(f"❌ Error: {sample_file} not found!")
        return 1

    # Create backup if .env.test exists
    if existing_file.exists():
        print(f"📦 Creating backup: {backup_file.name}")
        shutil.copy2(existing_file, backup_file)
    else:
        print("ℹ️  No existing .env.test found - will create new file from sample")
        existing_file = None

    # Merge files
    print(f"🔀 Merging {sample_file.name} with existing values...")
    preserved, added, updated = merge_env_files(
        sample_file, existing_file or Path("/dev/null"), existing_file or sample_file
    )

    # Write merged output
    if existing_file:
        print(f"✅ Updated {existing_file.name}")
    else:
        print(f"✅ Created {script_dir / '.env.test'} from sample")

    # Print statistics
    print("\n📊 Summary:")
    print(f"   • Preserved existing values: {preserved}")
    print(f"   • Added new variables: {added}")
    print(f"   • Total variables: {preserved + added}")

    if existing_file and existing_file.exists():
        print(f"\n💾 Backup saved: {backup_file.name}")

    print("\n✨ Done! Your .env.test has been updated.")
    print("   Review the changes and update any new variables with your actual values.")

    return 0


if __name__ == "__main__":
    exit(main())
