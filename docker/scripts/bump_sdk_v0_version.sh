#!/bin/bash

# Script to automate dependency version bumps in the Unstract project
# Author: Cascade
# Date: 2025-07-09

set -e

# Default paths
UNSTRACT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${UNSTRACT_ROOT}/backend"
PLATFORM_SERVICE_DIR="${UNSTRACT_ROOT}/platform-service"
PROMPT_SERVICE_DIR="${UNSTRACT_ROOT}/prompt-service"
FILESYSTEM_DIR="${UNSTRACT_ROOT}/unstract/filesystem"
TOOL_REGISTRY_DIR="${UNSTRACT_ROOT}/unstract/tool-registry"
CLASSIFIER_DIR="${UNSTRACT_ROOT}/tools/classifier"
STRUCTURE_DIR="${UNSTRACT_ROOT}/tools/structure"
TEXT_EXTRACTOR_DIR="${UNSTRACT_ROOT}/tools/text_extractor"

# Organized directory arrays
STRUCTURE_TOOL_DIRS=("$STRUCTURE_DIR")
CUSTOM_TOOL_DIRS=("$CLASSIFIER_DIR" "$TEXT_EXTRACTOR_DIR")
PACKAGE_DIRS=("$FILESYSTEM_DIR" "$TOOL_REGISTRY_DIR")
SERVICE_DIRS=("$BACKEND_DIR" "$PLATFORM_SERVICE_DIR" "$PROMPT_SERVICE_DIR")
ROOT_DIR="$UNSTRACT_ROOT"

# Additional files having version
SAMPLE_ENV_FILE="${BACKEND_DIR}/sample.env"
TOOL_REGISTRY_JSON_FILE="${TOOL_REGISTRY_DIR}/tool_registry_config/public_tools.json"

# Global variables
VERBOSE=false
DRY_RUN=false
RESET_MODE=false
BUMP_MODE=false
TARGET_VERSION=""

# Version bumping functions
bump_version() {
    local version="$1"
    local bump_type="$2"
    
    # If the bump_type is not a special keyword, return it as is
    if [[ "$bump_type" != "patch" && "$bump_type" != "minor" && "$bump_type" != "major" ]]; then
        echo "$bump_type"
        return
    fi
    
    # Split version into major, minor, patch
    IFS='.' read -r major minor patch <<< "$version"
    
    # Handle special bump types
    case "$bump_type" in
        patch)
            patch=$((patch + 1))
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
    esac
    
    echo "$major.$minor.$patch"
}

# Display usage information
usage() {
    echo "Usage: $0 --bump [options] | --reset [options]"
    echo ""
    echo "This script automates semantic version bumps for Unstract SDK and related tools."
    echo ""
    echo "Core Commands:"
    echo "  --bump           Perform the version bump."
    echo "  --target-version <version> Required with --bump. Specifies the new version."
    echo "                         Accepts 'major', 'minor', 'patch', or a specific version (e.g., 1.2.3)."
    echo "  --reset          Reset all changes made by this script."
    echo ""
    echo "Options:"
    echo "  -v, --verbose    Enable verbose logging."
    echo "  --dry-run        Run the script without making any changes."
    echo "  -h, --help       Display this help message."
    echo ""
    echo "Examples:"
    echo "  $0 --bump --verbose                                         # Update with verbose output"
    echo "  $0 --bump --dry-run                                         # Preview changes without applying them"
    echo "  $0 --reset --dry-run                                         # Preview what files would be reset"
    echo "  $0 --dry-run                                         # Preview changes without applying them"
    echo "  $0 --reset                                           # Reset all files modified by this script"
    echo "  $0 --reset --dry-run                                 # Preview what files would be reset"
    exit 1
}

# Parse command-line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --bump)
                BUMP_MODE=true
                shift
                ;;
            --target-version)
                if [[ -z "$2" || "$2" == -* ]]; then
                    echo "Error: --target-version requires an argument."
                    usage
                    exit 1
                fi
                TARGET_VERSION="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -d|--dry-run)
                DRY_RUN=true
                shift
                ;;
            --reset)
                RESET_MODE=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                echo "Unknown option: $1"
                usage
                ;;
        esac
    done
}



# Log messages when verbose mode is enabled
log() {
    if [[ "$VERBOSE" == true ]]; then
        echo "    DEBUG: $1"
    fi
}

# Check if a file exists
check_file() {
    if [[ ! -f "$1" ]]; then
        echo "Error: File not found: $1"
        exit 1
    fi
}

# Update structure tool version in sample.env
update_structure_tool_version() {
    local file="$1"
    local version_arg="$2"
    local old_url_version
    local old_tag_version
    local new_version

    echo "Processing structure tool..."

    # Check if file exists
    if [[ ! -f "$file" ]]; then
        echo "Warning: $file not found, skipping structure tool update"
        return
    fi

    log "Checking structure tool version in $file"
    check_file "$file"

    # NOTE: Currently we bump only patch version for tools
    if [[ "$version_arg" != *"."* ]]; then
        version_arg="patch"
        echo "Set target version for structure tool as $version_arg"
    fi

    # Extract current structure tool versions
    old_url_version=$(grep 'STRUCTURE_TOOL_IMAGE_URL' "$file" | grep -o '[0-9.]\+"$' | tr -d '"')
    old_tag_version=$(grep 'STRUCTURE_TOOL_IMAGE_TAG' "$file" | grep -o '[0-9.]\+"$' | tr -d '"')

    if [[ -z "$old_url_version" || -z "$old_tag_version" ]]; then
        echo "Error: Could not find structure tool version in $file"
        exit 1
    fi

    log "Found structure tool URL version: $old_url_version"
    log "Found structure tool TAG version: $old_tag_version"

    # Handle special version keywords
    if [[ "$version_arg" == "patch" || "$version_arg" == "minor" || "$version_arg" == "major" ]]; then
        new_version=$(bump_version "$old_url_version" "$version_arg")
        log "Auto-bumped structure tool version: $old_url_version -> $new_version ($version_arg)"
    else
        new_version="$version_arg"
    fi

    if [[ "$old_url_version" == "$new_version" && "$old_tag_version" == "$new_version" ]]; then
        echo "Structure tool version already at $new_version, skipping update"
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "Would update structure tool URL version from $old_url_version to $new_version in $file"
        echo "Would update structure tool TAG version from $old_tag_version to $new_version in $file"
    else
        echo "Updating structure tool versions from $old_url_version/$old_tag_version to $new_version in $file"
        sed -i "s/STRUCTURE_TOOL_IMAGE_URL=\"docker:unstract\/tool-structure:$old_url_version\"/STRUCTURE_TOOL_IMAGE_URL=\"docker:unstract\/tool-structure:$new_version\"/g" "$file"
        sed -i "s/STRUCTURE_TOOL_IMAGE_TAG=\"$old_tag_version\"/STRUCTURE_TOOL_IMAGE_TAG=\"$new_version\"/g" "$file"
    fi
}

# Update custom tool version and its SDK dependency
update_custom_tool_version() {
    local dir="$1"
    local version_arg="$2"
    local registry_json_file="$3"
    local tool_name=$(basename "$dir")
    local properties_json_file="${dir}/src/config/properties.json"
    local requirements_file="${dir}/requirements.txt"
    local old_version
    local new_version

    echo "Processing custom tool: $tool_name"

    log "Checking $tool_name version in $properties_json_file"
    check_file "$properties_json_file"

    # NOTE: Currently we bump only patch version for tools
    if [[ "$version_arg" != *"."* ]]; then
        version_arg="patch"
        echo "Set target version for custom tool $tool_name as $version_arg"
    fi

    # Fetch tool's version from properties.json
    old_version=$(grep -o '"toolVersion": "[0-9.]\+"' "$properties_json_file" | grep -o '[0-9.]\+')
    if [[ -z "$old_version" ]]; then
        echo "Error: Could not find $tool_name version in $properties_json_file"
        exit 1
    fi

    log "Found $tool_name version: $old_version"

    if [[ "$version_arg" == "patch" || "$version_arg" == "minor" || "$version_arg" == "major" ]]; then
        new_version=$(bump_version "$old_version" "$version_arg")
        log "Auto-bumped $tool_name version: $old_version -> $new_version ($version_arg)"
    else
        new_version="$version_arg"
    fi

    if [[ "$old_version" == "$new_version" ]]; then
        echo "$tool_name version already at $new_version, skipping update."
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "Would update $tool_name version from $old_version to $new_version in $properties_json_file"
        return
    fi

    # 1. Update the tool's own version in properties json
    echo "Updating $tool_name version from $old_version to $new_version in $properties_json_file"
    sed -i "s/\"toolVersion\": \"$old_version\"/\"toolVersion\": \"$new_version\"/g" "$properties_json_file"

    # 2. Update the tool's own version in registry json
    echo "Updating $tool_name version from $old_version to $new_version in $registry_json_file"

    adjusted_tool_name=$tool_name
    if [[ "$tool_name" == "classifier" ]]; then
        adjusted_tool_name="classify"
    fi

    # Modify the line after `"functionName": "$adjusted_tool_name"`
    sed -i "/\"functionName\": \"$adjusted_tool_name\"/{ n; s/\"toolVersion\": \"$old_version\"/\"toolVersion\": \"$new_version\"/; }" "$registry_json_file"
    # Modify the line `"image_url": "docker:unstract/tool-$tool_name:$old_version"`
    sed -i "s|\"image_url\": \"docker:unstract/tool-$tool_name:$old_version\"|\"image_url\": \"docker:unstract/tool-$tool_name:$new_version\"|" "$registry_json_file"
    # Modify the line after `"image_name": "unstract/tool-$tool_name"`
    sed -i "/\"image_name\": \"unstract\\/tool-$tool_name\"/{ n; s/\"image_tag\": \"$old_version\"/\"image_tag\": \"$new_version\"/; }" "$registry_json_file"

    # 3. Update the unstract-sdk version in the tool's requirements.txt
    if [[ -f "$requirements_file" ]]; then
        echo "Updating SDK version in $tool_name requirements.txt"
        update_sdk_version "$requirements_file" "$version_arg"
    fi
}

# Update SDK version in pyproject.toml or requirements.txt
update_sdk_version() {
    local file="$1"
    local version_arg="$2"
    local dir_name=$(dirname "$dir")
    local old_version
    local new_version
    local pattern
    local replacement

    echo "Processing SDK version for $dir_name..."

    # Check if file exists
    if [[ ! -f "$file" ]]; then
        echo "Warning: $file not found, skipping SDK update"
        return
    fi

    # Check if file has unstract-sdk dependency
    if ! grep -q "unstract-sdk" "$file"; then
        log "unstract-sdk dependency not found in $file, skipping"
        return
    fi

    log "Checking SDK version in $file"

    # Check for different SDK formats based on file type
    if grep -q 'unstract-sdk\[gcs, azure, aws\]' "$file"; then
        pattern='unstract-sdk\[gcs, azure, aws\]~='
        log "Found unstract-sdk[gcs, azure, aws] in $file"
    elif grep -q 'unstract-sdk\[azure\]' "$file"; then
        pattern='unstract-sdk\[azure\]~='
        log "Found unstract-sdk[azure] in $file"
    elif grep -q 'unstract-sdk\[aws\]' "$file"; then
        pattern='unstract-sdk\[aws\]~='
        log "Found unstract-sdk[aws] in $file"
    elif grep -q 'unstract-sdk~=' "$file"; then
        pattern='unstract-sdk~='
        log "Found unstract-sdk in $file"
    else
        echo "Warning: Could not identify unstract-sdk pattern in $file"
        return 1
    fi

    # Extract current SDK version using the identified pattern
    old_version=$(grep -o "${pattern}[0-9.]\+" "$file" | grep -o '[0-9.]\+')

    if [[ -z "$old_version" ]]; then
        echo "Error: Could not find unstract-sdk version in $file"
        return 1
    fi

    log "Found SDK version: $old_version"
    
    # Handle special version keywords
    if [[ "$version_arg" == "patch" || "$version_arg" == "minor" || "$version_arg" == "major" ]]; then
        new_version=$(bump_version "$old_version" "$version_arg")
        log "Auto-bumped SDK version: $old_version -> $new_version ($version_arg)"
    else
        new_version="$version_arg"
    fi
    
    if [[ "$old_version" == "$new_version" ]]; then
        echo "SDK version already at $new_version, skipping update in $file"
        return
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "Would update SDK version from $old_version to $new_version in $file"
    else
        echo "Updating SDK version from $old_version to $new_version in $file"
        # Use the detected pattern to update the version
        sed -i "s/${pattern}${old_version}/${pattern}${new_version}/g" "$file"
        
        # Also update any other references to the SDK version in the file
        sed -i "s/unstract-sdk\", specifier = \"~=$old_version/unstract-sdk\", specifier = \"~=$new_version/g" "$file"
    fi
}

# Generate or update uv.lock file in a directory
generate_uvlock() {
    local dir="$1"
    local uvlock_file="$dir/uv.lock"
    
    log "Processing uv lock for $dir..."

    # Check if pyproject.toml exists
    if [[ ! -f "$dir/pyproject.toml" ]]; then
        echo "Warning: pyproject.toml not found in $dir, skipping uv.lock generation"
        return 1
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "Would generate uv.lock file in $dir"
    else
        echo "Generating uv.lock file in $dir"
        # Use uv pip compile to generate the lock file
        (cd "$dir" && uv lock) || {
            echo "Error: Failed to generate uv.lock in $dir"
            return 1
        }
    fi
    
    return 0
}

# Reset a single file to its original state
reset_file() {
    local file="$1"
    local rel_path="${file#$UNSTRACT_ROOT/}"
    
    if [[ "$DRY_RUN" == true ]]; then
        echo "[DRY RUN] Would reset $file to its original state"
    elif [[ -f "$file" ]]; then
        echo "Resetting $file to its original state"
        (cd "$UNSTRACT_ROOT" && git checkout -- "$rel_path") || {
            echo "Warning: Failed to reset $file"
        }
    fi
}

# Reset changes in a specific directory
reset_directory_changes() {
    # Reset root directory
    reset_file "$UNSTRACT_ROOT/pyproject.toml"
    reset_file "$UNSTRACT_ROOT/uv.lock"

    # Reset service directories
    reset_file "$BACKEND_DIR/pyproject.toml"
    reset_file "$BACKEND_DIR/uv.lock"
    reset_file "$PLATFORM_SERVICE_DIR/pyproject.toml"
    reset_file "$PLATFORM_SERVICE_DIR/uv.lock"
    reset_file "$PROMPT_SERVICE_DIR/pyproject.toml"
    reset_file "$PROMPT_SERVICE_DIR/uv.lock"

    # Reset package directories
    reset_file "$FILESYSTEM_DIR/pyproject.toml"
    reset_file "$FILESYSTEM_DIR/uv.lock"
    reset_file "$TOOL_REGISTRY_DIR/pyproject.toml"
    reset_file "$TOOL_REGISTRY_DIR/uv.lock"

    # Reset custom tool directories
    reset_file "$CLASSIFIER_DIR/requirements.txt"
    reset_file "$CLASSIFIER_DIR/src/config/properties.json"
    reset_file "$TEXT_EXTRACTOR_DIR/requirements.txt"
    reset_file "$TEXT_EXTRACTOR_DIR/src/config/properties.json"

    # Reset structure tool directories
    reset_file "$SAMPLE_ENV_FILE"
    reset_file "$TOOL_REGISTRY_JSON_FILE"
}

# Process each directory based on flags
process_directories() {
    # If in reset mode, handle resets and exit
    if [[ "$RESET_MODE" == true ]]; then
        echo "[-] Reset mode: Restoring files to their original state..."
        
        # Prompt user for confirmation
        echo "This will reset ALL UNRELATED changes too in each modified file. Do you want to continue?"
        read -p "Enter 'yes' to proceed: " confirm
        
        if [[ "$confirm" != "yes" ]]; then
            echo "[!] Operation cancelled."
        else
            reset_directory_changes
            echo "[*] All changes have been reset"
        fi
        
        return
    fi

    # If not in bump mode, do nothing and exit
    if [[ "$BUMP_MODE" == false ]]; then
        return
    fi
    
    echo "[-] Processing all directories and files for version bump..."
    
    # 1. Process structure tool
    update_structure_tool_version "$SAMPLE_ENV_FILE" "$TARGET_VERSION"
    
    # 2. Process custom tools
    echo "[-] Processing custom tools..."
    for dir in "${CUSTOM_TOOL_DIRS[@]}"; do
        update_custom_tool_version "$dir" "$TARGET_VERSION" "$TOOL_REGISTRY_JSON_FILE"
    done
    
    # 3. Process packages (similar to services)
    echo "[-] Processing packages..."
    for dir in "${PACKAGE_DIRS[@]}"; do
        update_sdk_version "$dir/pyproject.toml" "$TARGET_VERSION"
        generate_uvlock "$dir"
    done

    # 4. Process services
    echo "[-] Processing services..."
    for dir in "${SERVICE_DIRS[@]}"; do
        update_sdk_version "$dir/pyproject.toml" "$TARGET_VERSION"
        generate_uvlock "$dir"
    done

    # 5. Process root directory
    echo "[-] Processing root directory..."
    update_sdk_version "$ROOT_DIR/pyproject.toml" "$TARGET_VERSION"
    generate_uvlock "$ROOT_DIR"

    echo "[*] Done."
}

# Main function
main() {
    # Parse command-line arguments
    parse_args "$@"

    # Check if a core command is provided
    if [[ "$BUMP_MODE" == false && "$RESET_MODE" == false ]]; then
        usage
        exit 1
    fi

    # Check if --target-version is provided with --bump
    if [[ "$BUMP_MODE" == true && -z "$TARGET_VERSION" ]]; then
        echo "[!] Error: --target-version is required when using --bump."
        usage
        exit 1
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        echo "[*] Running with options:"
        echo "      Reset Mode: $RESET_MODE"
        echo "      Dry Run: $DRY_RUN"
        echo "      Verbose: $VERBOSE"
        echo ""
    fi

    # Process directories based on specified options
    process_directories
}

# Execute the main function with all arguments
main "$@"