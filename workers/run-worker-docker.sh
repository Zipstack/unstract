#!/bin/bash
# =============================================================================
# Unstract Workers Runner Script - Docker Version
# =============================================================================
# This script is optimized for running workers inside Docker containers
# where all dependencies are pre-installed during image build.
#
# For local development, use run-worker.sh instead.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory - in Docker, everything runs from /app
WORKERS_DIR="/app"

# Default environment file
ENV_FILE="/app/.env"

# Available workers
declare -A WORKERS=(
    ["api"]="api_deployment"
    ["api-deployment"]="api_deployment"
    ["general"]="general"
    ["file"]="file_processing"
    ["file-processing"]="file_processing"
    ["callback"]="callback"
    ["all"]="all"
)

# Worker queue mappings
declare -A WORKER_QUEUES=(
    ["api_deployment"]="celery_api_deployments"
    ["general"]="celery"
    ["file_processing"]="file_processing,api_file_processing"
    ["callback"]="file_processing_callback,api_file_processing_callback"
)

# Worker health ports
declare -A WORKER_HEALTH_PORTS=(
    ["api_deployment"]="8080"
    ["general"]="8081"
    ["file_processing"]="8082"
    ["callback"]="8083"
)

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to load environment file
load_env() {
    local env_file=$1

    if [[ -f "$env_file" ]]; then
        print_status $GREEN "Loading environment from: $env_file"
        set -a  # automatically export all variables
        source "$env_file"
        set +a
    else
        print_status $YELLOW "Warning: Environment file not found: $env_file"
        print_status $YELLOW "Make sure required environment variables are set"
    fi
}

# Function to run a single worker
run_worker() {
    local worker_type=$1

    # Normalize worker type - convert hyphens to underscores for consistency
    case "$worker_type" in
        "api-deployment"|"api")
            worker_type="api_deployment"
            ;;
        "file-processing"|"file")
            worker_type="file_processing"
            ;;
        # general and callback stay the same
    esac

    # Set worker-specific environment variables
    export WORKER_TYPE="$worker_type"
    export WORKER_NAME="${worker_type}-worker"

    # Determine instance name
    local worker_instance_name="${worker_type}-worker"
    if [[ -n "$HOSTNAME" ]]; then
        # In Docker/K8s, use the container hostname
        worker_instance_name="${worker_type}-${HOSTNAME}"
    elif [[ -n "$WORKER_INSTANCE_ID" ]]; then
        worker_instance_name="${worker_type}-worker-${WORKER_INSTANCE_ID}"
    else
        # Default naming for production
        worker_instance_name="${worker_type}-worker-prod-01"
    fi

    # Get queues for this worker
    local queues="${WORKER_QUEUES[$worker_type]}"

    # Get health port
    local health_port="${WORKER_HEALTH_PORTS[$worker_type]}"

    # Set health port environment variable
    case "$worker_type" in
        "api_deployment")
            export API_DEPLOYMENT_HEALTH_PORT="${health_port}"
            export API_DEPLOYMENT_METRICS_PORT="${health_port}"
            ;;
        "general")
            export GENERAL_HEALTH_PORT="${health_port}"
            export GENERAL_METRICS_PORT="${health_port}"
            ;;
        "file_processing")
            export FILE_PROCESSING_HEALTH_PORT="${health_port}"
            export FILE_PROCESSING_METRICS_PORT="${health_port}"
            ;;
        "callback")
            export CALLBACK_HEALTH_PORT="${health_port}"
            export CALLBACK_METRICS_PORT="${health_port}"
            ;;
    esac

    # Determine autoscale settings
    local autoscale=""
    case "$worker_type" in
        "api_deployment")
            autoscale="${WORKER_API_DEPLOYMENT_AUTOSCALE:-4,1}"
            ;;
        "general")
            autoscale="${WORKER_GENERAL_AUTOSCALE:-6,2}"
            ;;
        "file_processing")
            autoscale="${WORKER_FILE_PROCESSING_AUTOSCALE:-8,2}"
            ;;
        "callback")
            autoscale="${WORKER_CALLBACK_AUTOSCALE:-4,1}"
            ;;
    esac

    print_status $GREEN "Starting $worker_type worker..."
    print_status $BLUE "Working Directory: /app"
    print_status $BLUE "Worker Name: $worker_instance_name"
    print_status $BLUE "Queues: $queues"
    print_status $BLUE "Health Port: $health_port"
    print_status $BLUE "Autoscale: $autoscale"

    # Use pre-installed Celery from Docker image
    # The virtual environment is already set up at /app/.venv during build
    exec /app/.venv/bin/celery -A worker worker \
        --loglevel="${LOG_LEVEL:-info}" \
        --queues="$queues" \
        --hostname="${worker_instance_name}@%h" \
        --autoscale="$autoscale"
}

# Main execution
# Docker containers pass the worker type as the first argument
WORKER_TYPE="${1:-general}"

# Load environment if exists
load_env "$ENV_FILE"

# Add PYTHONPATH for imports - include both /app and /unstract for packages
export PYTHONPATH="/app:/unstract/core/src:/unstract/connectors/src:/unstract/filesystem/src:/unstract/flags/src:/unstract/tool-registry/src:/unstract/tool-sandbox/src:/unstract/workflow-execution/src:${PYTHONPATH:-}"

# Run the worker
print_status $BLUE "Docker Unified Worker Starting..."
print_status $BLUE "Worker Type: $WORKER_TYPE"
run_worker "$WORKER_TYPE"
