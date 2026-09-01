#!/bin/bash
set -o pipefail

# Function to update the lockfile in a directory
#
# `uv lock --check` is the authoritative staleness test: it exits non-zero only
# when uv.lock is missing or no longer agrees with pyproject.toml, transitive
# local path dependencies included. Gating on it means a PR that already carries
# correct lockfiles is a genuine no-op, rather than a re-resolve that rewrites
# the tree and leaves the auto-commit step with nothing useful to push.
#
# `uv lock` (not `uv sync`) is what we want here: the workflow only ever commits
# uv.lock, so building a virtualenv and installing every package is wasted work
# and the single largest source of failures in this job.
update_lockfile() {
    local dir="$1"
    local file_path="$dir/pyproject.toml"

    if [[ ! -f "$file_path" ]]; then
        echo "[$dir] No pyproject.toml found in '$dir'"
        return 0
    fi

    # Run in a subshell so the directory change is scoped to this invocation
    (
        cd "$dir" || exit 1

        echo "[$dir] Checking whether uv.lock is up to date..."
        if uv lock --check >/dev/null 2>&1; then
            echo "[$dir] uv.lock is already up to date, nothing to do"
            exit 0
        fi

        echo "[$dir] uv.lock is out of date, regenerating..."
        uv lock 2>&1 | sed "s|^|[$dir] |"
    )
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
    "platform-service"
    "runner"
    "x2text-service"
    "unstract/filesystem"
    "unstract/core"
    "unstract/flags"
    "unstract/connectors"
    "unstract/sdk1"
    "unstract/tool-registry"
    "unstract/tool-sandbox"
    "unstract/workflow-execution"
    "tool-sidecar"
    "workers"
)

# If directories are passed as arguments, override the default
if [ "$#" -gt 0 ]; then
    directories=("$@")
fi

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

    # Wait for the specific process to finish
    if ! wait "$pid"; then
        echo "[$dir] Lock file generation failed. Killing other sub-processes..."
        kill $(list_descendants $$) 2>/dev/null || true
        exit 1
    fi
done
