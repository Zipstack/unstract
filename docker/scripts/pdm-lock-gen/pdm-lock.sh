#!/bin/bash
set -o pipefail

# Function to update the lockfile in a directory
update_lockfile() {
    dir="$1"
    file_path="$dir/pyproject.toml"

    if [[ ! -f "$file_path" ]]; then
        echo "[$dir] No pyproject.toml found in '$dir'"
        return 0
    fi

    echo "[$dir] Checking '$file_path' for changes against origin/main..."
    if ! git diff --quiet origin/main -- "$file_path"; then
        echo "[$dir] Changes detected in '$file_path', updating pdm.lock for '$dir' ..."

        # Move to the directory if it's not root
        if [[ "$dir" != "." ]]; then
            cd "$dir" || return 1
        fi

        # Set up virtual environment if not exists
        if [[ ! -d ".venv" ]]; then
            echo "[$dir] Creating virtual environment in directory: '$dir'"
            pdm venv create -w virtualenv --with-pip 2>&1 | sed "s|^|[$dir] |" || return 1
        else
            echo "[$dir] Virtual environment already exists in $dir"
        fi

        # Activate virtual environment
        source .venv/bin/activate 2>&1 | sed "s|^|[$dir] |" || return 1

        # HACK: https://github.com/pdm-project/pdm/issues/3199
        # Replace with checking the exit code directly once above issue is fixed
        lock_output=$(pdm lock --check 2>&1)
        if echo "$lock_output" | grep -q "WARNING: Lockfile is generated on an older version of PDM"; then
            echo "[$dir] Updating pdm.lock in '$dir' due to outdated version..."
            pdm lock -G :all -v 2>&1 | sed "s|^|[$dir] |" || return 1
        elif [[ $? -ne 0 ]]; then
            echo "[$dir] Updating pdm.lock in '$dir' due to detected changes..."
            pdm lock -G :all -v 2>&1 | sed "s|^|[$dir] |" || return 1
        else
            echo "[$dir] No changes required for pdm.lock in '$dir'."
        fi

        # Go back to root if moved to a subdirectory
        if [[ "$dir" != "." ]]; then
            cd - || return 1
        fi
    else
        echo "[$dir] No changes detected in '$file_path'"
    fi
}

# https://unix.stackexchange.com/a/124148
# Used to list child processes to kill them in case of an error
list_descendants ()
{
  local children=$(ps -o pid= --ppid "$1")

  for pid in $children
  do
    list_descendants "$pid"
  done

  echo "$children"
}

# Default directories list
directories=(
    "."
    "backend"
    "prompt-service"
    "worker"
    "unstract/filesystem"
    "unstract/core"
    "unstract/flags"
    "platform-service"
    "x2text-service"
    "unstract/connectors"
    "unstract/tool-sandbox"
)

# If directories are passed as arguments, override the default
if [ "$#" -gt 0 ]; then
    directories=("$@")
fi

# To compare against main branch
git fetch origin main

# Array to store the job PIDs and directories
pids=()
dirs=()

# Run lockfile updates in parallel
for dir in "${directories[@]}"; do
    update_lockfile "$dir" &
    pid=$!
    pids+=($pid)       # Add the PID of the background job to the array
    dirs+=("$dir")     # Add the corresponding directory to the array
done

# Wait for each background process to complete, exit on the first failure
for i in "${!pids[@]}"; do
    pid=${pids[$i]}
    dir=${dirs[$i]}
    echo "[$dir] Waiting for child process with PID: $pid..."

    # # Wait for the specific process to finish
    if ! wait "$pid"; then
        echo "[$dir] Lock file generation failed. Killing other sub-processes..."
        kill $(list_descendants $$) 2>/dev/null || true
        exit 1
    fi
done
