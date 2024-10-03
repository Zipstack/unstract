#!/bin/bash

# Default directories list
default_directories=(
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

# Check if directories are passed as arguments, otherwise use the default list
if [[ $# -eq 0 ]]; then
    directories=("${default_directories[@]}")
else
    directories=("$@")
fi

# To compare against main branch
git fetch origin main

for dir in "${directories[@]}"; do
    file_path="$dir/pyproject.toml"

    # Check if the pyproject.toml file exists
    if [[ ! -f "$file_path" ]]; then
        echo "No pyproject.toml found in $dir"
        continue  # Skip to the next iteration if the file does not exist
    fi

    # Check if there are changes in pyproject.toml against the main branch
    if git diff --quiet origin/main -- "$file_path"; then
        echo "No changes detected in $file_path"
        continue
    fi
    echo "Changes detected in $file_path, updating pdm.lock..."

    # Move to the directory if it's not the root
    if [[ "$dir" != "." ]]; then
        cd "$dir"
    fi

    # Set up virtual environment if not exists
    if [[ ! -d ".venv" ]]; then
        echo 'Creating virtual environment in directory: '"$dir"
        pdm venv create -w virtualenv --with-pip
    else
        echo "Virtual environment already exists in $dir"
    fi

    # Activate virtual environment
    source .venv/bin/activate

    # Update pdm.lock if required
    if pdm lock --check; then
        echo "No changes in dependencies, no need to run pdm lock."
    else
        echo "Changes detected, running pdm lock..."
        pdm lock -G :all -v
    fi

    # Go back to root if you moved to a subdirectory
    if [[ "$dir" != "." ]]; then
        cd -
    fi
done
