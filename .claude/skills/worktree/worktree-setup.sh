#!/bin/bash
#
# Worktree Setup Script for Unstract
# Copies necessary config files from source repo to a new worktree
#
# Usage: ./worktree-setup.sh <target_worktree_path> [source_repo_path]
#

set -euo pipefail

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
SOURCE_PATH="${2:-$(cd "$(dirname "$0")/../../.." && pwd)}"

if [ -z "$TARGET_PATH" ]; then
    show_usage 1
fi

# Convert to absolute paths (handle non-existent target)
if [ -d "$TARGET_PATH" ]; then
    TARGET_PATH=$(cd "$TARGET_PATH" && pwd)
else
    # Portable: construct absolute path relative to CWD without requiring realpath
    TARGET_PATH="$(cd "$(dirname "$TARGET_PATH")" 2>/dev/null && pwd)/$(basename "$TARGET_PATH")" \
      || TARGET_PATH="$(pwd)/$TARGET_PATH"
fi
if [ ! -d "$SOURCE_PATH" ]; then
    echo "Error: source repo path does not exist: $SOURCE_PATH"
    show_usage 1
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
echo "Env files: Copied=$copied, Skipped=$skipped, Missing=$missing"
echo ""

# ============================================================
# Step 2: Copy gitignored backend settings
# ============================================================
echo "Copying gitignored backend settings..."

SETTINGS_DIR="backend/backend/settings"
TRACKED_SETTINGS=("__init__.py" "base.py" "dev.py" "test.py")

settings_copied=0
settings_skipped=0

if [ -d "$SOURCE_PATH/$SETTINGS_DIR" ]; then
    for file in "$SOURCE_PATH/$SETTINGS_DIR"/*.py; do
        [ -f "$file" ] || continue
        filename=$(basename "$file")

        # Skip tracked files (these come from git)
        skip=false
        for tracked in "${TRACKED_SETTINGS[@]}"; do
            if [ "$filename" = "$tracked" ]; then
                skip=true
                break
            fi
        done
        $skip && continue

        # Copy gitignored settings file
        dest="$TARGET_PATH/$SETTINGS_DIR/$filename"
        mkdir -p "$(dirname "$dest")"

        if [ -f "$dest" ]; then
            if ! diff -q "$file" "$dest" > /dev/null 2>&1; then
                cp "$file" "$dest"
                echo "  [updated] $filename"
                settings_copied=$((settings_copied + 1))
            else
                echo "  [skipped] $filename (unchanged)"
                settings_skipped=$((settings_skipped + 1))
            fi
        else
            cp "$file" "$dest"
            echo "  [copied]  $filename"
            settings_copied=$((settings_copied + 1))
        fi
    done
else
    echo "  [warning] $SETTINGS_DIR not found in source"
fi

echo ""
echo "Settings: Copied=$settings_copied, Skipped=$settings_skipped"
echo ""

# ============================================================
# Step 3: Copy project-local Claude skills (gitignored ones)
# ============================================================
SKILLS_DIR=".claude/skills"
skills_copied=0
skills_skipped=0

if [ -d "$SOURCE_PATH/$SKILLS_DIR" ]; then
    echo "Copying project-local Claude skills..."

    for skill_dir in "$SOURCE_PATH/$SKILLS_DIR"/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        dest_dir="$TARGET_PATH/$SKILLS_DIR/$skill_name"

        # Skip if already present and identical
        if [ -d "$dest_dir" ] && diff -rq "$skill_dir" "$dest_dir" > /dev/null 2>&1; then
            echo "  [skipped] $skill_name/ (unchanged)"
            skills_skipped=$((skills_skipped + 1))
            continue
        fi

        mkdir -p "$dest_dir"
        # Trailing-dot trick: copies all contents including hidden files, but not . or ..
        cp -r "$skill_dir." "$dest_dir/" 2>/dev/null || true
        echo "  [copied]  $skill_name/"
        skills_copied=$((skills_copied + 1))
    done

    echo ""
    echo "Skills: Copied=$skills_copied, Skipped=$skills_skipped"
else
    echo "No $SKILLS_DIR directory found in source, skipping."
fi

echo ""
echo "Done!"
