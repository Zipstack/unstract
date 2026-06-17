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
# Canonical name of the PG-queue consumer worker (referenced in several maps
# and special-cases below; a constant keeps them in sync).
readonly PG_QUEUE_CONSUMER_TYPE="pg_queue_consumer"
# Canonical name of the PG-queue reaper (leader-elected recovery process).
readonly PG_QUEUE_REAPER_TYPE="pg_queue_reaper"
# Set alias that launches the whole PG-queue group (consumer + reaper) together.
readonly PG_QUEUE_SET="pg-queue"
# Log-tail alias for the Celery set: every worker EXCEPT the PG-queue members.
# Mirrors PG_QUEUE_SET so the two transports' logs can be tailed separately
# (-L celery vs -L pg-queue). Logs-only — the Celery set is *run* via 'all'.
readonly CELERY_SET="celery"

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
    # PG Queue consumer — polls Postgres (SKIP LOCKED), not RabbitMQ via Celery
    ["pg-queue-consumer"]="$PG_QUEUE_CONSUMER_TYPE"
    ["$PG_QUEUE_CONSUMER_TYPE"]="$PG_QUEUE_CONSUMER_TYPE"
    ["pg-consumer"]="$PG_QUEUE_CONSUMER_TYPE"
    # PG Queue reaper — leader-elected recovery loop (barrier-orphan sweep)
    ["reaper"]="$PG_QUEUE_REAPER_TYPE"
    ["pg-queue-reaper"]="$PG_QUEUE_REAPER_TYPE"
    ["$PG_QUEUE_REAPER_TYPE"]="$PG_QUEUE_REAPER_TYPE"
    # Set: launch the whole PG-queue group (consumer + reaper) in one shot
    ["$PG_QUEUE_SET"]="$PG_QUEUE_SET"
    ["pg"]="$PG_QUEUE_SET"
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
    # The PG queue (in pg_queue_message) this consumer polls — exported as
    # WORKER_PG_QUEUE_CONSUMER_QUEUE, not a Celery --queues value.
    ["$PG_QUEUE_CONSUMER_TYPE"]="notifications"
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
    # pg_queue_consumer: 8090 — reserved here, just past the 8080-8089 core
    # range and just below where pluggable-worker discovery starts allocating
    # (8091+, see below), so it collides with neither. The consumer binds it
    # only when WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT is exported (below); a bare
    # `python -m pg_queue_consumer` binds nothing.
    ["$PG_QUEUE_CONSUMER_TYPE"]="8090"
    # pg_queue_reaper: 8086 — the one free slot in the 8080-8090 band (8086 sits
    # between callback's 8085 and scheduler's 8087). Bound only when
    # WORKER_PG_REAPER_HEALTH_PORT is exported (below); a bare
    # `python -m pg_queue_reaper` binds nothing.
    ["$PG_QUEUE_REAPER_TYPE"]="8086"
)

# Opt-in workers: experimental and NOT part of the default "all" fleet, so
# they're started only on explicit request. Status shows them only when they
# are actually running, so a deliberate non-start isn't reported as a STOPPED
# failure (they'd otherwise show STOPPED after every `all`).
declare -A OPTIN_WORKERS=(
    ["$PG_QUEUE_CONSUMER_TYPE"]=1
    ["$PG_QUEUE_REAPER_TYPE"]=1
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
    pg-queue-consumer     Run PG-queue poll-loop consumer (opt-in; not part of 'all')
    reaper, pg-queue-reaper Run PG-queue reaper (leader-elected recovery; opt-in)
    pg, pg-queue          Run the PG-queue set (consumer + reaper) together
    all                   Run all workers (in separate processes, includes auto-discovered pluggable workers)

Note: Pluggable workers in pluggable_worker/ directory are automatically discovered and can be run by name.
Note: 'all' is the Celery worker set; 'pg-queue' is the PG-queue set. They are independent —
      run both in parallel for a dual-transport (strangler-fig) setup.
Note: pg-queue-consumer overrides: WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE (source worker whose
      tasks to load, default notification), WORKER_PG_QUEUE_CONSUMER_QUEUE (queue to poll),
      and WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT (liveness server port, default 8090).
Note: reaper overrides: WORKER_PG_ORCHESTRATOR_LEASE_SECONDS (lease window, default 10),
      WORKER_PG_REAPER_INTERVAL_SECONDS (cycle interval, default 5),
      WORKER_PG_REAPER_HEALTH_PORT (liveness server port, default 8086),
      WORKER_PG_REAPER_HEALTH_STALE_SECONDS (liveness staleness window, default 30).

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
    -L, --logs [WORKER]   Live-tail worker log files (all if WORKER omitted).
                          WORKER may also be a set: 'celery' (all but the
                          PG-queue members) or 'pg-queue' (consumer + reaper).
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

    # Tail just the Celery set's logs (excludes the PG-queue workers)
    $0 -L celery

    # Tail just the PG-queue set's logs (consumer + reaper)
    $0 -L pg-queue

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

            # Assign health port dynamically (starting from 8091; 8090 is
            # reserved for pg_queue_consumer, so the first pluggable worker
            # doesn't collide with it).
            if [[ -z "${WORKER_HEALTH_PORTS[$worker_name]:-}" ]]; then
                WORKER_HEALTH_PORTS["$worker_name"]=$((8091 + discovered_count))
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
    local worker_type=$1 pattern out rc
    # The PG-queue consumer and reaper run as `python -m <pkg>`, not a Celery
    # `<type>-worker@host` process, so they have no `-worker` token to anchor on.
    # Match the module invocation instead (covers both the `uv run python` parent
    # and the `python -m` child). Keeps --status / -k / -r working for them.
    if [[ "$worker_type" == "$PG_QUEUE_CONSUMER_TYPE" || "$worker_type" == "$PG_QUEUE_REAPER_TYPE" ]]; then
        pattern="-m[[:space:]]+${worker_type}([[:space:]]|\$)"
    else
        pattern="[^[:alnum:]_]${worker_type}-worker(@|-)"
    fi
    # pgrep exits 1 for "no match" (normal — absorbed) but >=2 for an
    # operational/regex error. Distinguish them: collapsing rc>=2 to empty would
    # make a live worker look absent (a -k no-op, or a duplicate spawn on -r).
    out=$(pgrep -f -- "$pattern")
    rc=$?
    if (( rc > 1 )); then
        print_status "$YELLOW" "warning: pgrep failed (rc=$rc) while matching $worker_type" >&2
    fi
    [[ -n "$out" ]] && printf '%s\n' "$out"
    return 0
}

# Returns get_worker_pids output as a single space-separated string with
# the trailing space stripped — the form xargs and `kill` want. Wrapping
# this avoids repeating the `tr | sed` pipeline at every caller.
get_worker_pids_oneline() {
    local worker_type=$1
    get_worker_pids "$worker_type" | tr '\n' ' ' | sed 's/ $//'
}

# Function to resolve canonical worker dir names from the WORKERS map
# (skips aliases and "all"). Includes discovered pluggable workers.
list_core_worker_dirs() {
    local seen=""
    for key in "${!WORKERS[@]}"; do
        local value="${WORKERS[$key]}"
        # Skip set aliases ("all", "pg-queue") — they're groups, not real worker
        # dirs/processes, so status must not list them as phantom STOPPED workers.
        if [[ "$value" == "all" || "$value" == "$PG_QUEUE_SET" ]]; then
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
    elif [[ "$requested" == "$CELERY_SET" ]]; then
        # Celery set logs = every worker EXCEPT the PG-queue members. Mirror of
        # the 'pg-queue' alias below, so the two transports' logs can be tailed
        # separately when both sets run side by side.
        for d in $(list_core_worker_dirs) $(list_pluggable_worker_dirs); do
            [[ "$d" == "$PG_QUEUE_CONSUMER_TYPE" || "$d" == "$PG_QUEUE_REAPER_TYPE" ]] && continue
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
        if [[ "$canonical" == "$PG_QUEUE_SET" ]]; then
            # The set alias maps to no single dir — tail both member logs.
            for d in "$PG_QUEUE_CONSUMER_TYPE" "$PG_QUEUE_REAPER_TYPE"; do
                local member_log
                member_log=$(resolve_log_file "$d")
                [[ -n "$member_log" ]] && log_files+=("$member_log")
            done
        else
            local f
            f=$(resolve_log_file "$canonical")
            if [[ -z "$f" ]]; then
                print_status $YELLOW "No log file found for $canonical. Did you start it with -d?"
                exit 0
            fi
            log_files+=("$f")
        fi
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
    pids=$(get_worker_pids_oneline "$worker_dir")
    if [[ -z "$pids" ]]; then
        print_status $YELLOW "  $worker_dir: not running"
        return 0
    fi
    print_status $YELLOW "  $worker_dir: killing $pids"
    # shellcheck disable=SC2086
    kill -TERM $pids || print_status $RED "  $worker_dir: kill -TERM failed"
    sleep 1
    local survivors
    survivors=$(get_worker_pids_oneline "$worker_dir")
    if [[ -n "$survivors" ]]; then
        # shellcheck disable=SC2086
        kill -KILL $survivors || print_status $RED "  $worker_dir: kill -KILL failed"
        sleep 1
        survivors=$(get_worker_pids_oneline "$worker_dir")
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
        pids=$(get_worker_pids_oneline "$worker")

        # Opt-in workers aren't part of `all`; only surface them when running
        # so an intentional non-start doesn't read as a STOPPED failure.
        if [[ -z "$pids" && -n "${OPTIN_WORKERS[$worker]:-}" ]]; then
            continue
        fi

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

    # PG queue consumer is a plain Python poll-loop (polls Postgres via
    # SKIP LOCKED, not a Celery/RabbitMQ worker) — override the celery command
    # with the bootstrapping launcher and route the queue via env.
    if [[ "$worker_type" == "$PG_QUEUE_CONSUMER_TYPE" ]]; then
        export WORKER_PG_QUEUE_CONSUMER_QUEUE="$queues"
        # The consumer registers ONE source worker's tasks (the launcher sets
        # WORKER_TYPE from this before `import worker`). Default: notification —
        # the worker that owns the first migrated leaf task,
        # send_webhook_notification; override to drain another worker's queue.
        export WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE="${WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE:-notification}"
        # Liveness HTTP server port (-p override wins, else the map default).
        # Exported so the launcher's main() opts into the health server.
        export WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT="${health_port:-${WORKER_HEALTH_PORTS[$worker_type]}}"
        cmd_args=("uv" "run" "python" "-m" "$PG_QUEUE_CONSUMER_TYPE")
    fi

    # PG queue reaper — a leader-elected SQL recovery loop (no Celery, no task
    # bootstrap). Override the celery command with the plain `python -m` entry.
    # Tunables (lease window, cycle interval) come from env. The liveness server
    # binds when WORKER_PG_REAPER_HEALTH_PORT is set (-p override wins, else the
    # map default) — exported so the reaper's main() opts in.
    if [[ "$worker_type" == "$PG_QUEUE_REAPER_TYPE" ]]; then
        export WORKER_PG_REAPER_HEALTH_PORT="${health_port:-${WORKER_HEALTH_PORTS[$worker_type]}}"
        cmd_args=("uv" "run" "python" "-m" "$PG_QUEUE_REAPER_TYPE")
    fi

    print_status $GREEN "Starting $worker_type worker..."
    print_status $BLUE "Directory: $worker_dir"
    print_status $BLUE "Worker Name: $worker_instance_name"
    print_status $BLUE "Queues: ${queues:-n/a}"
    # Show the effective port: a -p/--health-port override wins over the map.
    print_status $BLUE "Health Port: ${health_port:-${WORKER_HEALTH_PORTS[$worker_type]:-n/a}}"
    print_status $BLUE "Command: ${cmd_args[*]}"

    # Change to appropriate directory
    # For pluggable workers, stay at workers root to allow module imports
    # For core workers, change to worker directory
    if [[ -n "${PLUGGABLE_WORKERS[$worker_type]:-}" || "$worker_type" == "$PG_QUEUE_CONSUMER_TYPE" || "$worker_type" == "$PG_QUEUE_REAPER_TYPE" ]]; then
        # Run from the workers root so `python -m pg_queue_consumer` /
        # `python -m pg_queue_reaper` (and what they import) resolve.
        cd "$WORKERS_DIR"
    else
        cd "$worker_dir"
    fi

    if [[ "$detach" == "true" ]]; then
        # Run in background. Write to an ABSOLUTE log path ($worker_dir is
        # absolute) so the file lands where resolve_log_file() / -L / -C look,
        # regardless of cwd. Workers that run from the workers root (pluggable
        # workers, pg_queue_consumer) would otherwise drop a relative
        # "$worker_type.log" at the root, where -L/-C can't find it.
        local log_file="$worker_dir/$worker_type.log"
        nohup "${cmd_args[@]}" > "$log_file" 2>&1 &
        local pid=$!
        # set -e does not apply to backgrounded jobs, so a fork that dies on
        # startup (e.g. the consumer's require_tasks RuntimeError, an
        # `import worker` failure, a bad env cast) would still be reported as
        # "started" — and for pg_queue_consumer, which has no health port, a
        # dead process then just reads as absent in --status. Catch an
        # *immediate* exit. This is a best-effort fast-fail for crash-on-import
        # / bad-config faults (sub-second), NOT a connectivity check: a worker
        # that dies slowly (e.g. a broker connect timing out after >1s) still
        # passes here and surfaces later via its health port / --status. Run all
        # detached workers share it — an immediate crash can hit any worker type;
        # in `all` the subshells are backgrounded, so this 1s overlaps the
        # inter-launch sleep rather than serializing.
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            print_status $RED "$worker_type worker failed to start (PID $pid exited) — last log lines:"
            tail -n 20 "$log_file" 2>/dev/null
            return 1
        fi
        print_status $GREEN "$worker_type worker started in background (PID: $pid)"
        print_status $BLUE "Logs: $log_file"
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

# Function to run the PG-queue worker set (consumer + reaper) together.
# A set is multiple processes, so — like 'all' — it ALWAYS runs detached
# (it ignores -d/--detach; there's no foreground form). The PG-queue counterpart
# to 'all' (the Celery set): run both for a dual-transport (strangler-fig) setup.
# The reaper is a leader-elected singleton, so running it on several hosts is
# safe (only one wins the lease). Returns non-zero if any member dies on start —
# the reaper has no health port yet, so this launch check is the only
# programmatic startup signal a caller (systemd/CI) gets.
run_pg_queue_set() {
    local log_level=$1
    local concurrency=$2
    local pool_type=$3

    print_status $GREEN "Starting PG-queue set (consumer + reaper)..."
    local failed=0
    for worker in "$PG_QUEUE_CONSUMER_TYPE" "$PG_QUEUE_REAPER_TYPE"; do
        print_status $BLUE "Starting $worker in background..."
        # A FOREGROUND subshell: run_worker (detach=true) nohup-backgrounds the
        # actual worker and returns 1 on an immediate crash-on-start — so the
        # subshell's exit status IS that signal. The subshell isolates run_worker's
        # `cd` from this loop; the nohup'd worker survives the subshell exiting.
        # (A background `( … ) &` would lose the status — its `$!` is the launcher
        # subshell, which exits the instant it backgrounds the worker.)
        ( run_worker "$worker" "true" "$log_level" "$concurrency" "" "" "$pool_type" "" ) \
            || failed=1
    done
    if [[ $failed -ne 0 ]]; then
        print_status $RED "PG-queue set: a member failed to start — tearing down the set (see logs above)"
        # Don't leave a survivor: a restart-on-failure relaunch would spawn a
        # second instance on top of it (the consumer would double-poll Postgres).
        # Kill both members (the crashed one is already gone → no-op). Same
        # all-or-nothing discipline as the restart path.
        kill_one_worker "$PG_QUEUE_CONSUMER_TYPE"
        kill_one_worker "$PG_QUEUE_REAPER_TYPE"
        show_status
        return 1
    fi
    print_status $GREEN "PG-queue set started in background"
    show_status
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
    if [[ "${WORKERS[$WORKER_TYPE]:-}" == "$PG_QUEUE_SET" ]]; then
        # Restart the PG-queue set: kill both members, then fall through to the
        # launch path (which runs run_pg_queue_set since WORKER_TYPE is the set).
        # Aggregate kill failures (kill_one_worker returns 1 if a process survives
        # SIGKILL) and abort rather than relaunch over a survivor — a second
        # consumer would double-poll Postgres. Mirrors kill_workers' discipline.
        print_status $BLUE "Restarting PG-queue set..."
        restart_failed=0
        kill_one_worker "$PG_QUEUE_CONSUMER_TYPE" || restart_failed=1
        kill_one_worker "$PG_QUEUE_REAPER_TYPE" || restart_failed=1
        if [[ $restart_failed -ne 0 ]]; then
            print_status $RED "Cannot restart PG-queue set: a member survived SIGKILL; aborting to avoid duplicate processes"
            exit 1
        fi
    elif [[ -n "$WORKER_TYPE" && "$WORKER_TYPE" != "all" ]]; then
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
elif [[ "${WORKERS[$WORKER_TYPE]:-}" == "$PG_QUEUE_SET" ]]; then
    # The PG-queue set (consumer + reaper). Always backgrounded (multiple procs).
    # Propagate a member start-failure to the script exit code — the reaper has
    # no health port, so this is the only programmatic startup signal.
    run_pg_queue_set "$LOG_LEVEL" "$CONCURRENCY" "$POOL_TYPE" || exit 1
else
    # Resolve worker directory name from either WORKERS or PLUGGABLE_WORKERS
    WORKER_DIR_NAME="${WORKERS[$WORKER_TYPE]}"
    if [[ -z "$WORKER_DIR_NAME" ]]; then
        WORKER_DIR_NAME="${PLUGGABLE_WORKERS[$WORKER_TYPE]}"
    fi
    run_worker "$WORKER_DIR_NAME" "$DETACH" "$LOG_LEVEL" "$CONCURRENCY" "$CUSTOM_QUEUES" "$HEALTH_PORT" "$POOL_TYPE" "$CUSTOM_HOSTNAME"
fi
