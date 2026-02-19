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

# Available core workers (OSS)
declare -A WORKERS=(
    ["api"]="api_deployment"
    ["api-deployment"]="api_deployment"
    ["general"]="general"
    ["file"]="file_processing"
    ["file-processing"]="file_processing"
    ["callback"]="callback"
    ["notification"]="notification"
    ["log"]="log_consumer"
    ["log-consumer"]="log_consumer"
    ["scheduler"]="scheduler"
    ["schedule"]="scheduler"
    ["executor"]="executor"
    ["all"]="all"
)

# Pluggable workers will be auto-discovered at runtime
# Note: All workers use the main 'worker' module which routes to correct tasks via WORKER_TYPE env var
declare -A PLUGGABLE_WORKERS=()

# Worker queue mappings
declare -A WORKER_QUEUES=(
    ["api_deployment"]="celery_api_deployments"
    ["general"]="celery"
    ["file_processing"]="file_processing,api_file_processing"
    ["callback"]="file_processing_callback,api_file_processing_callback"
    ["notification"]="notifications,notifications_webhook,notifications_email,notifications_sms,notifications_priority"
    ["log_consumer"]="celery_log_task_queue"
    ["scheduler"]="scheduler"
    ["executor"]="executor"
)

# Worker health ports
declare -A WORKER_HEALTH_PORTS=(
    ["api_deployment"]="8080"
    ["general"]="8081"
    ["file_processing"]="8082"
    ["callback"]="8083"
    ["log_consumer"]="8084"
    ["notification"]="8085"
    ["scheduler"]="8087"
    ["executor"]="8088"
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

# Function to discover pluggable workers
discover_pluggable_workers() {
    local pluggable_dir="/app/pluggable_worker"

    # Silently return if pluggable_worker directory doesn't exist
    if [[ ! -d "$pluggable_dir" ]]; then
        return
    fi

    local discovered_count=0

    # Scan for directories with worker.py
    for worker_path in "$pluggable_dir"/*; do
        # Skip if not a directory
        if [[ ! -d "$worker_path" ]]; then
            continue
        fi

        local worker_name=$(basename "$worker_path")

        # Skip special directories (starting with _ or .)
        if [[ "$worker_name" == _* ]] || [[ "$worker_name" == .* ]]; then
            continue
        fi

        # Check if worker.py exists
        if [[ -f "$worker_path/worker.py" ]]; then
            # Register the pluggable worker
            PLUGGABLE_WORKERS["$worker_name"]="$worker_name"

            # Add hyphenated alias for convenience (e.g., bulk-download -> bulk_download)
            local hyphenated_name="${worker_name//_/-}"
            if [[ "$hyphenated_name" != "$worker_name" ]]; then
                PLUGGABLE_WORKERS["$hyphenated_name"]="$worker_name"
            fi

            # Set default queue if not already defined
            if [[ -z "${WORKER_QUEUES[$worker_name]:-}" ]]; then
                WORKER_QUEUES["$worker_name"]="$worker_name"
            fi

            # Assign health port dynamically (starting from 8090)
            if [[ -z "${WORKER_HEALTH_PORTS[$worker_name]:-}" ]]; then
                WORKER_HEALTH_PORTS["$worker_name"]=$((8090 + discovered_count))
            fi

            print_status $GREEN "Discovered pluggable worker: $worker_name"
            ((discovered_count+=1))
        fi
    done

    if [[ $discovered_count -gt 0 ]]; then
        print_status $BLUE "Total pluggable workers: $discovered_count"
    fi
}


# Function to resolve worker type (supports both core and pluggable workers)
resolve_worker_type() {
    local worker_type=$1

    # Check core workers first
    if [[ -n "${WORKERS[$worker_type]:-}" ]]; then
        echo "${WORKERS[$worker_type]}"
        return
    fi

    # Check pluggable workers
    if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
        echo "${PLUGGABLE_WORKERS[$worker_type]}"
        return
    fi

    # Return as-is if not found (will be validated later)
    echo "$worker_type"
}

# Function to detect worker type from command-line arguments
detect_worker_type_from_args() {
    local -n args_ref=$1

    # Look for --queues argument to infer worker type
    local queues=""
    local i=0
    while [[ $i -lt ${#args_ref[@]} ]]; do
        local arg="${args_ref[$i]}"
        case "$arg" in
            --queues=*)
                queues="${arg#--queues=}"
                break
                ;;
            --queues)
                ((i++))
                if [[ $i -lt ${#args_ref[@]} ]]; then
                    queues="${args_ref[$i]}"
                    break
                fi
                ;;
        esac
        ((i++))
    done

    # Map queue patterns to worker types
    case "$queues" in
        *"file_processing"*) echo "file_processing" ;;
        *"celery_api_deployments"*) echo "api_deployment" ;;
        *"file_processing_callback"*) echo "callback" ;;
        *"notifications"*) echo "notification" ;;
        *"celery_log_task_queue"*) echo "log_consumer" ;;
        *"scheduler"*) echo "scheduler" ;;
        *"executor"*) echo "executor" ;;
        *"celery"*) echo "general" ;;
        *) echo "general" ;; # fallback
    esac
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
        "log-consumer"|"log")
            worker_type="log_consumer"
            ;;
        # general, callback, and notification stay the same
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

    # Get queues for this worker - allow environment override
    local queues="${WORKER_QUEUES[$worker_type]}"
    case "$worker_type" in
        "api_deployment")
            queues="${CELERY_QUEUES_API_DEPLOYMENT:-$queues}"
            ;;
        "general")
            queues="${CELERY_QUEUES_GENERAL:-$queues}"
            ;;
        "file_processing")
            queues="${CELERY_QUEUES_FILE_PROCESSING:-$queues}"
            ;;
        "callback")
            queues="${CELERY_QUEUES_CALLBACK:-$queues}"
            ;;
        "notification")
            queues="${CELERY_QUEUES_NOTIFICATION:-$queues}"
            ;;
        "log_consumer")
            queues="${CELERY_QUEUES_LOG_CONSUMER:-$queues}"
            ;;
        "scheduler")
            queues="${CELERY_QUEUES_SCHEDULER:-$queues}"
            ;;
        "executor")
            queues="${CELERY_QUEUES_EXECUTOR:-$queues}"
            ;;
    esac

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
        "notification")
            export NOTIFICATION_HEALTH_PORT="${health_port}"
            export NOTIFICATION_METRICS_PORT="${health_port}"
            ;;
        "log_consumer")
            export LOG_CONSUMER_HEALTH_PORT="${health_port}"
            export LOG_CONSUMER_METRICS_PORT="${health_port}"
            ;;
        "scheduler")
            export SCHEDULER_HEALTH_PORT="${health_port}"
            export SCHEDULER_METRICS_PORT="${health_port}"
            ;;
        "executor")
            export EXECUTOR_HEALTH_PORT="${health_port}"
            export EXECUTOR_METRICS_PORT="${health_port}"
            ;;
        *)
            # Default for pluggable workers
            local worker_type_upper=$(echo "$worker_type" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            export "${worker_type_upper}_HEALTH_PORT=${health_port}"
            export "${worker_type_upper}_METRICS_PORT=${health_port}"
            ;;
    esac

    # Determine concurrency settings
    local concurrency=""
    case "$worker_type" in
        "api_deployment")
            concurrency="${WORKER_API_DEPLOYMENT_CONCURRENCY:-2}"
            ;;
        "general")
            concurrency="${WORKER_GENERAL_CONCURRENCY:-4}"
            ;;
        "file_processing")
            concurrency="${WORKER_FILE_PROCESSING_CONCURRENCY:-4}"
            ;;
        "callback")
            concurrency="${WORKER_CALLBACK_CONCURRENCY:-4}"
            ;;
        "notification")
            concurrency="${WORKER_NOTIFICATION_CONCURRENCY:-2}"
            ;;
        "log_consumer")
            concurrency="${WORKER_LOG_CONSUMER_CONCURRENCY:-2}"
            ;;
        "scheduler")
            concurrency="${WORKER_SCHEDULER_CONCURRENCY:-2}"
            ;;
        "executor")
            concurrency="${WORKER_EXECUTOR_CONCURRENCY:-2}"
            ;;
        *)
            # Default for pluggable workers or unknown types
            local worker_type_upper=$(echo "$worker_type" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            local worker_concurrency_var="WORKER_${worker_type_upper}_CONCURRENCY"
            concurrency="${!worker_concurrency_var:-2}"
            ;;
    esac

    print_status $GREEN "Starting $worker_type worker..."
    print_status $BLUE "Working Directory: /app"
    print_status $BLUE "Worker Name: $worker_instance_name"
    print_status $BLUE "Queues: $queues"
    print_status $BLUE "Health Port: $health_port"
    print_status $BLUE "Concurrency: $concurrency"

    # Build Celery command with configurable options
    # Use main worker module - it handles both core and pluggable workers via WORKER_TYPE
    local app_module="${CELERY_APP_MODULE:-worker}"

    # Initial command without specific args - they'll be resolved with priority system
    local celery_cmd="/app/.venv/bin/celery -A $app_module worker"
    local celery_args=""

    # =============================================================================
    # Hierarchical Configuration Resolution (4-tier priority system)
    # =============================================================================
    # Resolve worker-specific overrides using the hierarchical configuration pattern:
    # 1. Command-line arguments (highest priority)
    # 2. {WORKER_TYPE}_{SETTING_NAME} (high priority)
    # 3. CELERY_{SETTING_NAME} (medium priority)
    # 4. Default value (lowest priority)

    # Traditional environment-based command building (no CLI parsing needed)

    # Convert worker_type to uppercase for environment variable resolution
    local worker_type_upper=$(echo "$worker_type" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

    # Helper function for hierarchical configuration resolution (environment-based)
    resolve_config() {
        local setting_name=$1
        local default_value=$2

        # Check worker-specific setting (highest priority)
        local worker_specific_var="${worker_type_upper}_${setting_name}"
        local worker_value=$(eval echo "\${${worker_specific_var}:-}")
        if [[ -n "$worker_value" ]]; then
            echo "$worker_value"
            return
        fi

        # Check global Celery setting (medium priority)
        local global_var="CELERY_${setting_name}"
        local global_value=$(eval echo "\${${global_var}:-}")
        if [[ -n "$global_value" ]]; then
            echo "$global_value"
            return
        fi

        # Use default value (lowest priority)
        echo "$default_value"
    }

    # Resolve configuration using environment variables only
    local resolved_queues="$queues"
    celery_args="$celery_args --queues=$resolved_queues"

    # Resolve log level
    local resolved_loglevel="${CELERY_LOG_LEVEL:-${LOG_LEVEL:-INFO}}"
    celery_args="$celery_args --loglevel=$resolved_loglevel"

    # Resolve hostname
    local resolved_hostname="${CELERY_HOSTNAME:-${worker_instance_name}@%h}"
    celery_args="$celery_args --hostname=$resolved_hostname"

    # Apply hierarchical configuration for pool type
    local pool_type=$(resolve_config "POOL_TYPE" "prefork")
    # Override with legacy CELERY_POOL for backward compatibility
    pool_type="${CELERY_POOL:-$pool_type}"
    celery_args="$celery_args --pool=$pool_type"

    # Configure concurrency with hierarchical resolution
    local resolved_concurrency=$(resolve_config "CONCURRENCY" "$concurrency")
    # Apply legacy CELERY_CONCURRENCY
    resolved_concurrency="${CELERY_CONCURRENCY:-$resolved_concurrency}"
    celery_args="$celery_args --concurrency=$resolved_concurrency"

    # Apply hierarchical configuration for optional parameters

    # Prefetch multiplier
    local prefetch_multiplier=$(resolve_config "PREFETCH_MULTIPLIER" "")
    prefetch_multiplier="${CELERY_PREFETCH_MULTIPLIER:-$prefetch_multiplier}"
    if [[ -n "$prefetch_multiplier" ]]; then
        celery_args="$celery_args --prefetch-multiplier=$prefetch_multiplier"
    fi

    # Max tasks per child
    local max_tasks_per_child=$(resolve_config "MAX_TASKS_PER_CHILD" "")
    max_tasks_per_child="${CELERY_MAX_TASKS_PER_CHILD:-$max_tasks_per_child}"
    if [[ -n "$max_tasks_per_child" ]]; then
        celery_args="$celery_args --max-tasks-per-child=$max_tasks_per_child"
    fi

    # Task time limit
    local time_limit=$(resolve_config "TASK_TIME_LIMIT" "")
    time_limit="${CELERY_TIME_LIMIT:-$time_limit}"
    if [[ -n "$time_limit" ]]; then
        celery_args="$celery_args --time-limit=$time_limit"
    fi

    # Task soft time limit
    local soft_time_limit=$(resolve_config "TASK_SOFT_TIME_LIMIT" "")
    soft_time_limit="${CELERY_SOFT_TIME_LIMIT:-$soft_time_limit}"
    if [[ -n "$soft_time_limit" ]]; then
        celery_args="$celery_args --soft-time-limit=$soft_time_limit"
    fi

    # Add gossip, mingle, and heartbeat control flags based on environment variables
    # Default: gossip=true, mingle=true, heartbeat=true (Celery defaults)

    if [[ "${CELERY_WORKER_GOSSIP:-true}" == "false" ]]; then
        celery_args="$celery_args --without-gossip"
    fi

    if [[ "${CELERY_WORKER_MINGLE:-true}" == "false" ]]; then
        celery_args="$celery_args --without-mingle"
    fi

    if [[ "${CELERY_WORKER_HEARTBEAT:-true}" == "false" ]]; then
        celery_args="$celery_args --without-heartbeat"
    fi

    # Add any additional custom Celery arguments
    if [[ -n "$CELERY_EXTRA_ARGS" ]]; then
        celery_args="$celery_args $CELERY_EXTRA_ARGS"
    fi

    # Execute the command
    exec $celery_cmd $celery_args
}

# Main execution
# Load environment first for any needed variables
load_env "$ENV_FILE"

# Discover pluggable workers (cloud-only)
discover_pluggable_workers

# Add PYTHONPATH for imports - include both /app and /unstract for packages
export PYTHONPATH="/app:/unstract/core/src:/unstract/connectors/src:/unstract/filesystem/src:/unstract/flags/src:/unstract/tool-registry/src:/unstract/tool-sandbox/src:/unstract/workflow-execution/src:${PYTHONPATH:-}"

# Two-path logic: Full Celery command vs Traditional worker type
if [[ "$1" == *"celery"* ]] || [[ "$1" == *".venv"* ]]; then
    # =============================================================================
    # PATH 1: Full Celery Command Detected - Use Directly
    # =============================================================================
    print_status $BLUE "🚀 Full Celery command detected - executing directly"

    # Extract worker type for environment setup
    ALL_ARGS=("$@")
    WORKER_TYPE=$(detect_worker_type_from_args ALL_ARGS)

    print_status $BLUE "Detected worker type: $WORKER_TYPE"
    print_status $BLUE "Command: $*"

    # Set essential environment variables for worker identification
    export WORKER_TYPE="$WORKER_TYPE"
    export WORKER_NAME="${WORKER_TYPE}-worker"

    # Set worker instance name for identification
    if [[ -n "$HOSTNAME" ]]; then
        worker_instance_name="${WORKER_TYPE}-${HOSTNAME}"
    elif [[ -n "$WORKER_INSTANCE_ID" ]]; then
        worker_instance_name="${WORKER_TYPE}-worker-${WORKER_INSTANCE_ID}"
    else
        worker_instance_name="${WORKER_TYPE}-worker-docker"
    fi
    export WORKER_NAME="$worker_instance_name"

    # Set health port environment variable based on worker type
    case "$WORKER_TYPE" in
        "api_deployment")
            export API_DEPLOYMENT_HEALTH_PORT="8080"
            export API_DEPLOYMENT_METRICS_PORT="8080"
            ;;
        "general")
            export GENERAL_HEALTH_PORT="8081"
            export GENERAL_METRICS_PORT="8081"
            ;;
        "file_processing")
            export FILE_PROCESSING_HEALTH_PORT="8082"
            export FILE_PROCESSING_METRICS_PORT="8082"
            ;;
        "callback")
            export CALLBACK_HEALTH_PORT="8083"
            export CALLBACK_METRICS_PORT="8083"
            ;;
        "notification")
            export NOTIFICATION_HEALTH_PORT="8085"
            export NOTIFICATION_METRICS_PORT="8085"
            ;;
        "log_consumer")
            export LOG_CONSUMER_HEALTH_PORT="8084"
            export LOG_CONSUMER_METRICS_PORT="8084"
            ;;
        "scheduler")
            export SCHEDULER_HEALTH_PORT="8087"
            export SCHEDULER_METRICS_PORT="8087"
            ;;
        "executor")
            export EXECUTOR_HEALTH_PORT="8088"
            export EXECUTOR_METRICS_PORT="8088"
            ;;
        *)
            # Default for pluggable workers - use dynamic port from WORKER_HEALTH_PORTS
            health_port="${WORKER_HEALTH_PORTS[$WORKER_TYPE]:-8090}"
            worker_type_upper=$(echo "$WORKER_TYPE" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
            export "${worker_type_upper}_HEALTH_PORT=$health_port"
            export "${worker_type_upper}_METRICS_PORT=$health_port"
            ;;
    esac

    print_status $GREEN "✅ Executing Celery command with highest priority..."

    # Execute the full command directly - Celery will handle all arguments
    exec "$@"

else
    # =============================================================================
    # PATH 2: Traditional Worker Type - Build from Environment
    # =============================================================================
    REQUESTED_WORKER_TYPE="${1:-general}"

    # Resolve worker type (supports both core and pluggable workers)
    WORKER_TYPE=$(resolve_worker_type "$REQUESTED_WORKER_TYPE")

    print_status $BLUE "🔧 Traditional worker type detected: $REQUESTED_WORKER_TYPE"
    if [[ "$WORKER_TYPE" != "$REQUESTED_WORKER_TYPE" ]]; then
        print_status $BLUE "   Resolved to: $WORKER_TYPE"
    fi
    print_status $BLUE "Building command from environment variables..."

    # Use existing run_worker function for environment-based building
    run_worker "$WORKER_TYPE"
fi
