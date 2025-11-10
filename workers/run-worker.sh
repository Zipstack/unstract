#!/bin/bash
# =============================================================================
# Unstract Workers Runner Script
# =============================================================================
# This script provides a convenient way to run individual or multiple workers
# with proper environment configuration and health monitoring.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKERS_DIR="$SCRIPT_DIR"

# Default environment file
ENV_FILE="$WORKERS_DIR/.env"

# Available workers
declare -A WORKERS=(
    ["api"]="api-deployment"
    ["api-deployment"]="api-deployment"
    ["general"]="general"
    ["file"]="file_processing"
    ["file-processing"]="file_processing"
    ["callback"]="callback"
    ["log"]="log_consumer"
    ["log-consumer"]="log_consumer"
    ["logs"]="log_consumer"
    ["notification"]="notification"
    ["notifications"]="notification"
    ["notify"]="notification"
    ["scheduler"]="scheduler"
    ["schedule"]="scheduler"
    ["all"]="all"
)

# Pluggable workers will be auto-discovered at runtime
declare -A PLUGGABLE_WORKERS=()

# Worker queue mappings
declare -A WORKER_QUEUES=(
    ["api-deployment"]="celery_api_deployments"
    ["general"]="celery"
    ["file_processing"]="file_processing,api_file_processing"
    ["callback"]="file_processing_callback,api_file_processing_callback"
    ["log_consumer"]="celery_log_task_queue"
    ["notification"]="notifications,notifications_webhook,notifications_email,notifications_sms,notifications_priority"
    ["scheduler"]="scheduler"
)

# Worker health ports
declare -A WORKER_HEALTH_PORTS=(
    ["api-deployment"]="8080"
    ["general"]="8081"
    ["file_processing"]="8082"
    ["callback"]="8083"
    ["log_consumer"]="8084"
    ["notification"]="8085"
    ["scheduler"]="8087"
)

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] WORKER_TYPE

Run Unstract Celery workers with proper environment configuration.

WORKER_TYPE:
    api, api-deployment    Run API deployment worker
    general               Run general worker (webhooks, background tasks)
    file, file-processing Run file processing worker
    callback              Run callback worker
    log, log-consumer     Run log consumer worker
    notification, notify  Run notification worker
    scheduler, schedule   Run scheduler worker (scheduled pipeline tasks)
    all                   Run all workers (in separate processes, includes auto-discovered pluggable workers)

Note: Pluggable workers in pluggable_worker/ directory are automatically discovered and can be run by name.

OPTIONS:
    -e, --env-file FILE   Use specific environment file (default: .env)
    -d, --detach          Run worker in background (daemon mode)
    -l, --log-level LEVEL Set log level (DEBUG, INFO, WARNING, ERROR)
    -c, --concurrency N   Set worker concurrency (default: auto)
    -q, --queues QUEUES   Override default queues (comma-separated)
    -p, --health-port N   Override health check port
    -P, --pool TYPE       Set Celery pool type (threads, prefork, gevent, solo, eventlet)
    -n, --hostname NAME   Set custom worker hostname/name
    -k, --kill            Kill running workers and exit
    -s, --status          Show status of running workers
    -h, --help            Show this help message

EXAMPLES:
    # Run API deployment worker
    $0 api

    # Run general worker with debug logging
    $0 -l DEBUG general

    # Run file processing worker in background
    $0 -d file

    # Run with custom environment file
    $0 -e production.env all

    # Run with custom concurrency
    $0 -c 4 general

    # Run with custom worker name (useful for scaling)
    $0 -n api-01 api
    $0 -n api-02 api

    # Run with specific pool type
    $0 -P prefork file
    $0 --pool threads general

    # Check worker status
    $0 -s

    # Kill all running workers
    $0 -k

ENVIRONMENT:
    The script will load environment variables from .env file if present.
    Required variables:
    - INTERNAL_SERVICE_API_KEY
    - INTERNAL_API_BASE_URL
    - CELERY_BROKER_BASE_URL
    - DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (for PostgreSQL result backend)

    Plugin availability is detected dynamically via plugin registry.
    See sample.env for full configuration options.

HEALTH CHECKS:
    Each worker exposes a health check endpoint:
    - API Deployment: http://localhost:8080/health
    - General: http://localhost:8081/health
    - File Processing: http://localhost:8082/health
    - Callback: http://localhost:8083/health
    - Log Consumer: http://localhost:8084/health
    - Notification: http://localhost:8085/health
    - Scheduler: http://localhost:8087/health
    - Pluggable workers: http://localhost:8090+/health (auto-assigned ports)

EOF
}

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
    local pluggable_dir="$WORKERS_DIR/pluggable_worker"

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

            # Add shorthand alias (e.g., bulk -> bulk_download)
            local first_part="${worker_name%%_*}"
            if [[ "$first_part" != "$worker_name" ]]; then
                PLUGGABLE_WORKERS["$first_part"]="$worker_name"
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
            ((discovered_count++))
        fi
    done

    if [[ $discovered_count -gt 0 ]]; then
        print_status $BLUE "Total pluggable workers: $discovered_count"
    fi
}

# Function to validate environment
validate_env() {
    local required_vars=(
        "INTERNAL_SERVICE_API_KEY"
        "INTERNAL_API_BASE_URL"
        "CELERY_BROKER_BASE_URL"
        "DB_HOST"
        "DB_USER"
        "DB_PASSWORD"
        "DB_NAME"
    )

    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        print_status $RED "Error: Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            print_status $RED "  - $var"
        done
        print_status $YELLOW "Please check your .env file or set these variables manually"
        exit 1
    fi
}

# Function to get worker PIDs
get_worker_pids() {
    local worker_type=$1
    pgrep -f "uv run celery.*worker.*$worker_type" || true
}

# Function to kill workers
kill_workers() {
    print_status $YELLOW "Killing all running workers..."

    for worker in "${!WORKERS[@]}"; do
        if [[ "$worker" == "all" ]]; then
            continue
        fi

        local worker_dir="${WORKERS[${worker}]}"
        local pids=$(pgrep -f "uv run celery.*worker" || true)

        if [[ -n "$pids" ]]; then
            print_status $YELLOW "Killing worker processes: $pids"
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep 2
            # Force kill if still running
            echo "$pids" | xargs kill -KILL 2>/dev/null || true
        fi
    done

    print_status $GREEN "All workers stopped"
}

# Function to show worker status
show_status() {
    print_status $BLUE "Worker Status:"
    echo "=============="

    local workers_to_check="api-deployment general file_processing callback log_consumer notification scheduler"

    # Add discovered pluggable workers
    if [[ ${#PLUGGABLE_WORKERS[@]} -gt 0 ]]; then
        for pluggable_name in "${!PLUGGABLE_WORKERS[@]}"; do
            local canonical_name="${PLUGGABLE_WORKERS[$pluggable_name]}"
            # Only add canonical names (skip aliases)
            if [[ "$pluggable_name" == "$canonical_name" ]]; then
                workers_to_check="$workers_to_check $canonical_name"
            fi
        done
    fi

    for worker in $workers_to_check; do
        local worker_dir="$WORKERS_DIR/$worker"
        local health_port="${WORKER_HEALTH_PORTS[$worker]}"
        local pids=$(get_worker_pids "$worker")

        echo -n "  $worker: "

        if [[ -n "$pids" ]]; then
            print_status $GREEN "RUNNING (PID: $pids)"

            # Check health endpoint if possible
            if command -v curl >/dev/null 2>&1; then
                local health_url="http://localhost:$health_port/health"
                if curl -s --max-time 2 "$health_url" >/dev/null 2>&1; then
                    echo "    Health: http://localhost:$health_port/health - OK"
                else
                    echo "    Health: http://localhost:$health_port/health - UNREACHABLE"
                fi
            fi
        else
            print_status $RED "STOPPED"
        fi
    done
}

# Function to run a single worker
run_worker() {
    local worker_type=$1
    local detach=$2
    local log_level=$3
    local concurrency=$4
    local custom_queues=$5
    local health_port=$6
    local pool_type=$7
    local custom_hostname=$8

    # Determine worker directory (handle pluggable workers)
    local worker_dir
    case "$worker_type" in
        "bulk_download")
            # Pluggable worker - use subdirectory
            worker_dir="$WORKERS_DIR/pluggable_worker/$worker_type"
            ;;
        *)
            # Core worker - use root directory
            worker_dir="$WORKERS_DIR/$worker_type"
            ;;
    esac

    if [[ ! -d "$worker_dir" ]]; then
        print_status $RED "Error: Worker directory not found: $worker_dir"

        # Provide helpful message for pluggable workers
        if [[ "$worker_type" == "bulk_download" ]]; then
            echo ""
            echo -e "${YELLOW}This is a cloud-only pluggable worker.${NC}"
            echo -e "Make sure:"
            echo -e "  1. CLOUD_DEPLOYMENT=true is set in your environment"
            echo -e "  2. The pluggable_worker/$worker_type folder exists"
            echo ""
        fi

        exit 1
    fi

    # Set worker-specific environment variables
    export WORKER_NAME="${worker_type}-worker"
    export WORKER_TYPE="$(echo "$worker_type" | tr '-' '_')"  # Convert hyphens to underscores for Python module names
    export LOG_LEVEL="${log_level:-INFO}"

    # Set CLOUD_DEPLOYMENT for pluggable workers
    case "$worker_type" in
        "bulk_download")
            export CLOUD_DEPLOYMENT=true
            print_status $BLUE "Cloud deployment enabled for pluggable worker"
            ;;
    esac

    # Set health port if specified
    if [[ -n "$health_port" ]]; then
        case "$worker_type" in
            "api-deployment")
                export API_DEPLOYMENT_HEALTH_PORT="$health_port"
                ;;
            "general")
                export GENERAL_HEALTH_PORT="$health_port"
                ;;
            "file_processing")
                export FILE_PROCESSING_HEALTH_PORT="$health_port"
                ;;
            "callback")
                export CALLBACK_HEALTH_PORT="$health_port"
                ;;
            "log_consumer")
                export LOG_CONSUMER_HEALTH_PORT="$health_port"
                ;;
            "notification")
                export NOTIFICATION_HEALTH_PORT="$health_port"
                ;;
            "scheduler")
                export SCHEDULER_HEALTH_PORT="$health_port"
                ;;
            "bulk_download")
                export BULK_DOWNLOAD_HEALTH_PORT="$health_port"
                ;;
        esac
    fi

    # Determine queues
    local queues="${custom_queues:-${WORKER_QUEUES[$worker_type]}}"

    # Build meaningful worker name
    local worker_instance_name="${worker_type}-worker"
    if [[ -n "$custom_hostname" ]]; then
        worker_instance_name="$custom_hostname"
    elif [[ -n "$WORKER_INSTANCE_ID" ]]; then
        worker_instance_name="${worker_type}-worker-${WORKER_INSTANCE_ID}"
    fi

    # Determine celery app module path (handle pluggable workers)
    local celery_app_module
    case "$worker_type" in
        "bulk_download")
            # Pluggable worker - use full module path
            celery_app_module="pluggable_worker.${worker_type}.worker"
            ;;
        *)
            # Core worker - use worker module
            celery_app_module="worker"
            ;;
    esac

    # Build celery command
    local cmd_args=(
        "uv" "run" "celery" "-A" "$celery_app_module" "worker"
        "--loglevel=${log_level:-info}"
        "--queues=$queues"
        "--hostname=${worker_instance_name}@%h"
    )

    # Add pool type if specified
    if [[ -n "$pool_type" ]]; then
        cmd_args+=("--pool=$pool_type")
    fi

    # Add concurrency if specified
    if [[ -n "$concurrency" ]]; then
        cmd_args+=("--concurrency=$concurrency")
    fi

    # Add concurrency for production-like setup
    if [[ -z "$concurrency" ]]; then
        case "$worker_type" in
            "api-deployment")
                cmd_args+=("--concurrency=2")
                ;;
            "general")
                cmd_args+=("--concurrency=4")
                ;;
            "file_processing")
                cmd_args+=("--concurrency=4")
                ;;
            "callback")
                cmd_args+=("--concurrency=4")
                ;;
            "log_consumer")
                cmd_args+=("--concurrency=2")
                ;;
            "notification")
                cmd_args+=("--concurrency=2")
                ;;
            "scheduler")
                cmd_args+=("--concurrency=2")
                ;;
            "bulk_download")
                cmd_args+=("--concurrency=2")
                ;;
        esac
    fi

    print_status $GREEN "Starting $worker_type worker..."
    print_status $BLUE "Directory: $worker_dir"
    print_status $BLUE "Worker Name: $worker_instance_name"
    print_status $BLUE "Queues: $queues"
    print_status $BLUE "Health Port: ${WORKER_HEALTH_PORTS[$worker_type]}"
    print_status $BLUE "Command: ${cmd_args[*]}"

    # Change to appropriate directory
    # For pluggable workers, stay at workers root to allow module imports
    # For core workers, change to worker directory
    case "$worker_type" in
        "bulk_download")
            cd "$WORKERS_DIR"
            ;;
        *)
            cd "$worker_dir"
            ;;
    esac

    if [[ "$detach" == "true" ]]; then
        # Run in background
        nohup "${cmd_args[@]}" > "$worker_type.log" 2>&1 &
        local pid=$!
        print_status $GREEN "$worker_type worker started in background (PID: $pid)"
        print_status $BLUE "Logs: $worker_dir/$worker_type.log"
    else
        # Run in foreground
        exec "${cmd_args[@]}"
    fi
}

# Function to run all workers
run_all_workers() {
    local detach=$1
    local log_level=$2
    local concurrency=$3
    local pool_type=$4

    print_status $GREEN "Starting all workers..."

    # Define core workers
    local core_workers="api-deployment general file_processing callback log_consumer notification scheduler"

    # Add discovered pluggable workers
    if [[ ${#PLUGGABLE_WORKERS[@]} -gt 0 ]]; then
        print_status $BLUE "Including pluggable workers in 'all' mode"

        # Get unique pluggable worker names (skip aliases)
        local pluggable_list=""
        for key in "${!PLUGGABLE_WORKERS[@]}"; do
            local value="${PLUGGABLE_WORKERS[$key]}"
            # Only add if it's the canonical name (not an alias)
            if [[ "$key" == "$value" ]]; then
                pluggable_list="$pluggable_list $value"
            fi
        done

        core_workers="$core_workers$pluggable_list"
    fi

    # Always run all workers in background when using "all"
    for worker in $core_workers; do
        print_status $BLUE "Starting $worker worker in background..."

        # Run each worker in background
        (
            run_worker "$worker" "true" "$log_level" "$concurrency" "" "" "$pool_type" ""
        ) &

        sleep 2  # Give each worker time to start
    done

    if [[ "$detach" != "true" ]]; then
        print_status $GREEN "All workers started. Press Ctrl+C to stop all workers."
        print_status $BLUE "Worker status:"
        sleep 3
        show_status

        # Wait for any background job to finish (they won't unless killed)
        wait
    else
        print_status $GREEN "All workers started in background"
        show_status
    fi
}

# Parse command line arguments
DETACH=false
LOG_LEVEL=""
CONCURRENCY=""
CUSTOM_QUEUES=""
HEALTH_PORT=""
POOL_TYPE=""
CUSTOM_HOSTNAME=""
KILL_WORKERS=false
SHOW_STATUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        -d|--detach)
            DETACH=true
            shift
            ;;
        -l|--log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -c|--concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        -q|--queues)
            CUSTOM_QUEUES="$2"
            shift 2
            ;;
        -p|--health-port)
            HEALTH_PORT="$2"
            shift 2
            ;;
        -P|--pool)
            POOL_TYPE="$2"
            shift 2
            ;;
        -n|--hostname)
            CUSTOM_HOSTNAME="$2"
            shift 2
            ;;
        -k|--kill)
            KILL_WORKERS=true
            shift
            ;;
        -s|--status)
            SHOW_STATUS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            print_status $RED "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            WORKER_TYPE="$1"
            shift
            ;;
    esac
done

# Handle special actions
if [[ "$KILL_WORKERS" == "true" ]]; then
    kill_workers
    exit 0
fi

if [[ "$SHOW_STATUS" == "true" ]]; then
    show_status
    exit 0
fi

# Validate worker type
if [[ -z "$WORKER_TYPE" ]]; then
    print_status $RED "Error: Worker type is required"
    usage
    exit 1
fi

# Load environment
load_env "$ENV_FILE"

# Discover pluggable workers
discover_pluggable_workers

# Validate worker type (check both core and pluggable workers)
if [[ -z "${WORKERS[$WORKER_TYPE]}" ]] && [[ -z "${PLUGGABLE_WORKERS[$WORKER_TYPE]}" ]]; then
    print_status $RED "Error: Unknown worker type: $WORKER_TYPE"
    print_status $BLUE "Available core workers: ${!WORKERS[*]}"
    if [[ ${#PLUGGABLE_WORKERS[@]} -gt 0 ]]; then
        # Show unique pluggable worker names (not aliases)
        pluggable_names=""
        for key in "${!PLUGGABLE_WORKERS[@]}"; do
            value="${PLUGGABLE_WORKERS[$key]}"
            if [[ "$key" == "$value" ]]; then
                pluggable_names="$pluggable_names $value"
            fi
        done
        print_status $BLUE "Available pluggable workers:$pluggable_names"
    fi
    exit 1
fi

# Validate environment
validate_env

# Add PYTHONPATH for imports
export PYTHONPATH="$WORKERS_DIR:${PYTHONPATH:-}"

# Run the requested worker(s)
if [[ "$WORKER_TYPE" == "all" ]]; then
    run_all_workers "$DETACH" "$LOG_LEVEL" "$CONCURRENCY" "$POOL_TYPE"
else
    # Resolve worker directory name from either WORKERS or PLUGGABLE_WORKERS
    WORKER_DIR_NAME="${WORKERS[$WORKER_TYPE]}"
    if [[ -z "$WORKER_DIR_NAME" ]]; then
        WORKER_DIR_NAME="${PLUGGABLE_WORKERS[$WORKER_TYPE]}"
    fi
    run_worker "$WORKER_DIR_NAME" "$DETACH" "$LOG_LEVEL" "$CONCURRENCY" "$CUSTOM_QUEUES" "$HEALTH_PORT" "$POOL_TYPE" "$CUSTOM_HOSTNAME"
fi
