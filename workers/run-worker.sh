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

# Worker type constant for the executor worker
readonly EXECUTOR_WORKER_TYPE="executor"
readonly IDE_CALLBACK_WORKER_TYPE="ide_callback"

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
    ["${EXECUTOR_WORKER_TYPE}"]="${EXECUTOR_WORKER_TYPE}"
    ["ide-callback"]="${IDE_CALLBACK_WORKER_TYPE}"
    ["${IDE_CALLBACK_WORKER_TYPE}"]="${IDE_CALLBACK_WORKER_TYPE}"
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
    ["${EXECUTOR_WORKER_TYPE}"]="celery_executor_legacy"
    ["${IDE_CALLBACK_WORKER_TYPE}"]="${IDE_CALLBACK_WORKER_TYPE}"
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
    ["${EXECUTOR_WORKER_TYPE}"]="8088"
    ["${IDE_CALLBACK_WORKER_TYPE}"]="8089"
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
    executor              Run executor worker (extraction execution tasks)
    ide-callback          Run IDE callback worker (Prompt Studio post-execution callbacks)
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
    -r, --restart         Kill matching worker(s) then relaunch (with WORKER_TYPE,
                          restarts only that worker; without it, restarts all)
    -s, --status          Show status of running workers
    -L, --logs [WORKER]   Live-tail worker log files (all if WORKER omitted)
    -C, --clear-logs      Delete worker .log files created by -d / 'all' runs
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

    # Live-tail all worker logs
    $0 -L

    # Tail just one worker's log
    $0 -L general

    # Wipe out old log files
    $0 -C

    # Restart all workers
    $0 -r -P prefork

    # Restart just one worker
    $0 -r general -l DEBUG

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
    Workers can optionally bind an HTTP health server on the port assigned
    via {WORKER}_HEALTH_PORT env vars (8080-8089 by default). It's used by
    K8s liveness probes in production but is NOT load-bearing locally —
    'run-worker.sh -s' only reports whether the Celery process is alive.

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
            ((discovered_count++)) || true
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
# Anchors the match on the hostname value's start (preceded by a non-word
# character) so e.g. "callback" doesn't also match "ide_callback". The
# trailing `(@|-)` covers both Celery hostname forms emitted by run_worker:
#   --hostname=callback-worker@%h         (default, no WORKER_INSTANCE_ID)
#   --hostname=callback-worker-${id}@%h   (when WORKER_INSTANCE_ID is set)
get_worker_pids() {
    local worker_type=$1
    pgrep -f -- "[^[:alnum:]_]${worker_type}-worker(@|-)" || true
}

# Function to resolve canonical worker dir names from the WORKERS map
# (skips aliases and "all"). Includes discovered pluggable workers.
list_core_worker_dirs() {
    local seen=""
    for key in "${!WORKERS[@]}"; do
        local value="${WORKERS[$key]}"
        if [[ "$value" == "all" ]]; then
            continue
        fi
        if [[ "$seen" == *" $value "* ]]; then
            continue
        fi
        seen="$seen $value "
        echo "$value"
    done
}

list_pluggable_worker_dirs() {
    for key in "${!PLUGGABLE_WORKERS[@]}"; do
        local value="${PLUGGABLE_WORKERS[$key]}"
        if [[ "$key" == "$value" ]]; then
            echo "$value"
        fi
    done
}

# Function to resolve the log file path for a given canonical worker dir.
# Core workers live at WORKERS_DIR/$dir/$dir.log; pluggable workers
# live at WORKERS_DIR/pluggable_worker/$dir/$dir.log.
resolve_log_file() {
    local worker_dir=$1
    local core_path="$WORKERS_DIR/$worker_dir/$worker_dir.log"
    local pluggable_path="$WORKERS_DIR/pluggable_worker/$worker_dir/$worker_dir.log"
    if [[ -f "$core_path" ]]; then
        echo "$core_path"
    elif [[ -f "$pluggable_path" ]]; then
        echo "$pluggable_path"
    fi
}

# Function to tail one or all worker log files (-L|--logs)
tail_logs() {
    local requested=$1  # may be empty → tail all
    local log_files=()

    if [[ -z "$requested" || "$requested" == "all" ]]; then
        for d in $(list_core_worker_dirs) $(list_pluggable_worker_dirs); do
            local f
            f=$(resolve_log_file "$d")
            [[ -n "$f" ]] && log_files+=("$f")
        done
    else
        # Resolve alias (e.g. "api" → "api-deployment") via WORKERS / PLUGGABLE_WORKERS
        local canonical="${WORKERS[$requested]:-${PLUGGABLE_WORKERS[$requested]:-}}"
        if [[ -z "$canonical" || "$canonical" == "all" ]]; then
            print_status $RED "Error: Unknown worker type for logs: $requested"
            print_status $BLUE "Tip: omit the worker type to tail all logs"
            exit 1
        fi
        local f
        f=$(resolve_log_file "$canonical")
        if [[ -z "$f" ]]; then
            print_status $YELLOW "No log file found for $canonical. Did you start it with -d?"
            exit 0
        fi
        log_files+=("$f")
    fi

    if [[ ${#log_files[@]} -eq 0 ]]; then
        print_status $YELLOW "No log files found. Workers must be started in detached mode (-d or 'all') for logs to be written to files."
        exit 0
    fi

    print_status $BLUE "Tailing ${#log_files[@]} log file(s) — Ctrl+C to stop"
    for f in "${log_files[@]}"; do
        print_status $GREEN "  $f"
    done
    exec tail -F "${log_files[@]}"
}

# Function to delete worker log files (-C|--clear-logs)
clear_logs() {
    local count=0
    for d in $(list_core_worker_dirs) $(list_pluggable_worker_dirs); do
        local f
        f=$(resolve_log_file "$d")
        if [[ -n "$f" ]]; then
            rm -f "$f"
            print_status $GREEN "Removed: $f"
            ((count++)) || true
        fi
    done
    if [[ $count -eq 0 ]]; then
        print_status $YELLOW "No worker log files to clear"
    else
        print_status $BLUE "Cleared $count log file(s)"
    fi
}

# Function to kill a single worker by its canonical dir name.
# Uses the anchored matcher from get_worker_pids so callback vs ide_callback
# don't bleed into each other. Surfaces kill failures (EPERM, ESRCH) and
# verifies the processes are gone before reporting success.
kill_one_worker() {
    local worker_dir=$1
    local pids
    pids=$(get_worker_pids "$worker_dir" | tr '\n' ' ' | sed 's/ $//')
    if [[ -z "$pids" ]]; then
        print_status $YELLOW "  $worker_dir: not running"
        return 0
    fi
    print_status $YELLOW "  $worker_dir: killing $pids"
    # shellcheck disable=SC2086
    kill -TERM $pids || print_status $RED "  $worker_dir: kill -TERM failed"
    sleep 1
    local survivors
    survivors=$(get_worker_pids "$worker_dir" | tr '\n' ' ' | sed 's/ $//')
    if [[ -n "$survivors" ]]; then
        # shellcheck disable=SC2086
        kill -KILL $survivors || print_status $RED "  $worker_dir: kill -KILL failed"
        sleep 1
        survivors=$(get_worker_pids "$worker_dir" | tr '\n' ' ' | sed 's/ $//')
        if [[ -n "$survivors" ]]; then
            print_status $RED "  $worker_dir: survivors after SIGKILL: $survivors"
            return 1
        fi
    fi
    return 0
}

# Function to kill all known workers. Iterates the canonical dir list and
# delegates to kill_one_worker so the anchored matcher is the single source
# of truth — avoids killing unrelated `celery worker` processes on the host.
kill_workers() {
    print_status $YELLOW "Killing all running workers..."
    local any_failed=0
    local workers_to_kill
    workers_to_kill="$(list_core_worker_dirs) $(list_pluggable_worker_dirs)"
    for worker in $workers_to_kill; do
        kill_one_worker "$worker" || any_failed=1
    done
    if [[ $any_failed -eq 0 ]]; then
        print_status $GREEN "All workers stopped"
    else
        print_status $RED "One or more workers could not be stopped"
        return 1
    fi
}

# Function to show worker status
show_status() {
    print_status $BLUE "Worker Status:"
    echo "=============="

    # Derive list from WORKERS (skips aliases & "all") so adding a new
    # worker in one place keeps status in sync. Pluggable workers included.
    local workers_to_check
    workers_to_check="$(list_core_worker_dirs) $(list_pluggable_worker_dirs)"

    for worker in $workers_to_check; do
        local pids
        pids=$(get_worker_pids "$worker" | tr '\n' ' ' | sed 's/ $//')

        printf '  %-22s ' "$worker:"

        if [[ -n "$pids" ]]; then
            local count
            count=$(echo "$pids" | wc -w)
            print_status $GREEN "RUNNING ($count proc, PID: $pids)"
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
    if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
        # Pluggable worker - use subdirectory
        worker_dir="$WORKERS_DIR/pluggable_worker/$worker_type"
    else
        # Core worker - use root directory
        worker_dir="$WORKERS_DIR/$worker_type"
    fi

    if [[ ! -d "$worker_dir" ]]; then
        print_status $RED "Error: Worker directory not found: $worker_dir"

        # Provide helpful message for pluggable workers
        if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
            echo ""
            echo -e "${YELLOW}This is a cloud-only pluggable worker.${NC}"
            echo -e "Make sure:"
            echo -e "  1. The pluggable_worker/$worker_type folder exists"
            echo -e "  2. The worker module has a valid worker.py file"
            echo ""
        fi

        exit 1
    fi

    # Set worker-specific environment variables
    export WORKER_NAME="${worker_type}-worker"
    export WORKER_TYPE="$(echo "$worker_type" | tr '-' '_')"  # Convert hyphens to underscores for Python module names
    export LOG_LEVEL="${log_level:-INFO}"

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
            "${EXECUTOR_WORKER_TYPE}")
                export EXECUTOR_HEALTH_PORT="$health_port"
                ;;
            "${IDE_CALLBACK_WORKER_TYPE}")
                export IDE_CALLBACK_HEALTH_PORT="$health_port"
                ;;
            *)
                # Handle pluggable workers dynamically
                if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
                    worker_type_upper=$(echo "$worker_type" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
                    export "${worker_type_upper}_HEALTH_PORT=$health_port"
                fi
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
    if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
        # Pluggable worker - use full module path
        celery_app_module="pluggable_worker.${worker_type}.worker"
    else
        # Core worker - use worker module
        celery_app_module="worker"
    fi

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
            "${EXECUTOR_WORKER_TYPE}")
                cmd_args+=("--concurrency=2")
                ;;
            "${IDE_CALLBACK_WORKER_TYPE}")
                cmd_args+=("--concurrency=2")
                ;;
            *)
                # Default for pluggable and other workers
                if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
                    cmd_args+=("--concurrency=2")
                fi
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
    if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" ]]; then
        cd "$WORKERS_DIR"
    else
        cd "$worker_dir"
    fi

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
    local core_workers="api-deployment general file_processing callback log_consumer notification scheduler executor ide_callback"

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
LOGS_MODE=false
CLEAR_LOGS_MODE=false
RESTART_MODE=false

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
        -L|--logs)
            LOGS_MODE=true
            shift
            ;;
        -C|--clear-logs)
            CLEAR_LOGS_MODE=true
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
        -r|--restart)
            RESTART_MODE=true
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
    discover_pluggable_workers
    show_status
    exit 0
fi

if [[ "$LOGS_MODE" == "true" ]]; then
    discover_pluggable_workers
    tail_logs "$WORKER_TYPE"
    exit 0
fi

if [[ "$CLEAR_LOGS_MODE" == "true" ]]; then
    discover_pluggable_workers
    clear_logs
    exit 0
fi

# Restart = kill matching + fall through to the normal launch path.
# - If WORKER_TYPE is set (and not "all"), kill only that worker.
# - Otherwise kill everything; the launch path will treat the unset
#   WORKER_TYPE as "all" once we set it below.
if [[ "$RESTART_MODE" == "true" ]]; then
    discover_pluggable_workers
    if [[ -n "$WORKER_TYPE" && "$WORKER_TYPE" != "all" ]]; then
        restart_target_dir="${WORKERS[$WORKER_TYPE]:-${PLUGGABLE_WORKERS[$WORKER_TYPE]:-}}"
        if [[ -z "$restart_target_dir" ]]; then
            print_status $RED "Error: Unknown worker type for restart: $WORKER_TYPE"
            exit 1
        fi
        print_status $BLUE "Restarting $restart_target_dir..."
        kill_one_worker "$restart_target_dir"
    else
        kill_workers
        WORKER_TYPE="all"
    fi
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
