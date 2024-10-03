#!/bin/bash

# Function to update the lockfile in a directory
update_lockfile() {
    dir="$1"
    file_path="$dir/pyproject.toml"

    if [[ ! -f "$file_path" ]]; then
        echo "[$dir] No pyproject.toml found in $dir"
        return
    fi

    echo "[$dir] Checking $file_path for changes against origin/main..."
    if ! git diff --quiet origin/main -- "$file_path"; then
        echo "[$dir] Changes detected in $file_path, updating pdm.lock for $dir..."

        # Move to the directory if it's not root
        if [[ "$dir" != "." ]]; then
            cd "$dir"
        fi

        # Set up virtual environment if not exists
        if [[ ! -d ".venv" ]]; then
            echo '[$dir] Creating virtual environment in directory: '"$dir"
            pdm venv create -w virtualenv --with-pip
        else
            echo "[$dir] Virtual environment already exists in $dir"
        fi

        # Activate virtual environment
        source .venv/bin/activate

        # Perform lockfile update if required
        if pdm lock --check; then
            echo "[$dir] No changes required for pdm.lock in $dir"
        else
            echo "[$dir] Updating pdm.lock in $dir..."
            pdm lock -G :all -v
        fi

        # Go back to root if moved to a subdirectory
        if [[ "$dir" != "." ]]; then
            cd -
        fi
    else
        echo "[$dir] No changes detected in $file_path"
    fi
}


# Default directories list
directories=(
    "."
    "backend"
    "prompt-service"
    "worker"
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


# Run lockfile updates in parallel
for dir in "${directories[@]}"; do
    update_lockfile "$dir" &
done

# Wait for all background processes to complete
wait
