#!/usr/bin/env bash

# Usage: ./migrate-to-v2.sh

set -o nounset # exit if a variable is not set
set -o errexit # exit for any command failure"

# text color escape codes (\033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
green_text='\033[32m'
red_text='\033[31m'
default_text='\033[39m'
yellow_text='\033[33m'

# Function to check and create virtual environment
activate_venv() {
    if [[ ! -d ".venv" ]]; then
        echo "No .venv found, please create one and install dependencies. Refer 'run-platform.sh' or 'dev-env-cli.sh";
        exit 1;
    else
        echo "Virtual environment found. Activating..."
        source .venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }
    fi
}

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
manage_script_dir=$(readlink -f "$script_dir/../../")
root_dir=$(readlink -f "$manage_script_dir/..")

# Configure environment variables for all services
echo -e "${blue_text}Configuring environment variables for the migration${default_text}"
"$root_dir/run-platform.sh" -e || { echo "Failed to configure environment"; exit 1; }

cd $manage_script_dir
activate_venv

# This implementation is easier than docker compose run sanity checks and usage parameters
echo -e "${blue_text}Running schema creation command...${default_text}"
python manage.py create_schema || { echo "Schema creation failed"; exit 1; }

echo -e "${blue_text}Running schema migration command...${default_text}"
python manage.py migrate || { echo "Schema migration failed"; exit 1; }

echo -e "${blue_text}Running data migration command...${default_text}"
SCHEMAS_TO_MIGRATE=_ALL_ python manage.py migrate_to_v2 || { echo "Data migration failed"; exit 1; }
