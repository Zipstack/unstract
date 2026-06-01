#!/usr/bin/env bash
set -uo pipefail
# Note: pipefail without -e — one task's failure must not abort the loop.

INTERVAL="${LOG_HISTORY_CONSUMER_INTERVAL:-5}"

# Task 1: log history consumer (existing).
DEFAULT_LOG_HISTORY_CMD="/app/.venv/bin/python /app/log_consumer/process_log_history.py"
LOG_HISTORY_CMD="${TASK_TRIGGER_COMMAND:-$DEFAULT_LOG_HISTORY_CMD}"

# Task 2: notification buffer flush (UNS-611 clubbed dispatch).
# The endpoint short-circuits on an empty PENDING set, so polling on the same
# 5s tick is cheap. Real dispatch cadence is gated by NOTIFICATION_CLUB_INTERVAL
# on the backend (rows precompute flush_after at enqueue time).
DEFAULT_BUFFER_FLUSH_CMD="/app/.venv/bin/python /app/log_consumer/process_notification_buffer.py"
BUFFER_FLUSH_CMD="${NOTIFICATION_BUFFER_TASK_COMMAND:-$DEFAULT_BUFFER_FLUSH_CMD}"

echo "=========================================="
echo "Log Consumer Scheduler Starting"
echo "=========================================="
echo "Interval: ${INTERVAL} seconds"
echo "Task 1 (log history): ${LOG_HISTORY_CMD}"
echo "Task 2 (notification buffer flush): ${BUFFER_FLUSH_CMD}"
echo "=========================================="

cleanup() {
    echo ""
    echo "=========================================="
    echo "Scheduler received shutdown signal"
    echo "Exiting gracefully..."
    echo "=========================================="
    return 0
}

# The trap exits after cleanup runs; cleanup itself returns so the function
# has an explicit terminal return (no unreachable code after exit).
trap 'cleanup; exit 0' SIGTERM SIGINT

run_task() {
    # $1 = display name, $2 = command. Returns the command's exit code but
    # never propagates failure — the caller logs it and moves on.
    local task_name="$1"
    local cmd="$2"
    local exit_code=0
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] Triggering ${task_name}..."
    if eval "${cmd}" 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] ✓ ${task_name} OK"
    else
        exit_code=$?
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] ✗ ${task_name} failed with exit code ${exit_code}"
    fi
    return "${exit_code}"
}

run_count=0

while true; do
    run_count=$((run_count + 1))

    run_task "process_log_history" "${LOG_HISTORY_CMD}"
    run_task "process_notification_buffer" "${BUFFER_FLUSH_CMD}"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sleeping for ${INTERVAL} seconds..."
    echo ""

    sleep "${INTERVAL}" &
    wait $!
done
