#!/bin/bash
#
# Worktree Setup Script for Unstract
# Copies necessary config files from source repo to a new worktree
#
# Usage: ./scripts/worktree-setup.sh <target_worktree_path> [source_repo_path]
#

set -e

show_usage() {
    echo "Usage: $0 <target_worktree_path> [source_repo_path]"
    echo ""
    echo "Arguments:"
    echo "  target_worktree_path  Path to the new worktree"
    echo "  source_repo_path      Path to source repo (defaults to script's parent dir)"
    exit "${1:-0}"
}

# Handle help flag
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage 0
fi

TARGET_PATH="$1"
SOURCE_PATH="${2:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ -z "$TARGET_PATH" ]; then
    show_usage 1
fi

# Convert to absolute paths (handle non-existent target)
if [ -d "$TARGET_PATH" ]; then
    TARGET_PATH=$(cd "$TARGET_PATH" && pwd)
else
    # For new paths, resolve relative to current dir
    TARGET_PATH=$(realpath -m "$TARGET_PATH" 2>/dev/null || echo "$TARGET_PATH")
fi
SOURCE_PATH=$(cd "$SOURCE_PATH" && pwd)

echo "Copying config files from unstract repo..."
echo "  Source: $SOURCE_PATH"
echo "  Target: $TARGET_PATH"
echo ""

# Files to copy (relative to repo root)
CONFIG_FILES=(
    # Service .env files
    "backend/.env"
    "frontend/.env"
    "platform-service/.env"
    "prompt-service/.env"
    "runner/.env"
    "workers/.env"
    "x2text-service/.env"
    # Docker config files
    "docker/.env"
    "docker/essentials.env"
    "docker/compose.override.yaml"
    "docker/proxy_overrides.yaml"
)

copied=0
skipped=0
missing=0

for file in "${CONFIG_FILES[@]}"; do
    src="$SOURCE_PATH/$file"
    dest="$TARGET_PATH/$file"

    if [ -f "$src" ]; then
        # Create directory if needed
        mkdir -p "$(dirname "$dest")"

        if [ -f "$dest" ]; then
            # File exists, check if different
            if ! diff -q "$src" "$dest" > /dev/null 2>&1; then
                cp "$src" "$dest"
                echo "  [updated] $file"
                copied=$((copied + 1))
            else
                echo "  [skipped] $file (unchanged)"
                skipped=$((skipped + 1))
            fi
        else
            cp "$src" "$dest"
            echo "  [copied]  $file"
            copied=$((copied + 1))
        fi
    else
        echo "  [missing] $file (not found in source)"
        missing=$((missing + 1))
    fi
done

echo ""
echo "Done! Copied: $copied, Skipped: $skipped, Missing: $missing"

if [ $missing -gt 0 ]; then
    echo ""
    echo "Note: Missing files may need to be created manually or may not exist in your setup."
fi
