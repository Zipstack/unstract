#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${LOG_HISTORY_CONSUMER_INTERVAL:-5}"
TASK_NAME="process_log_history"

# Task trigger command - can be overridden via environment variable
DEFAULT_TRIGGER_CMD="/app/.venv/bin/python /app/log_consumer/process_log_history.py"
TRIGGER_CMD="${TASK_TRIGGER_COMMAND:-$DEFAULT_TRIGGER_CMD}"

echo "=========================================="
echo "Log History Scheduler Starting"
echo "=========================================="
echo "Task: ${TASK_NAME}"
echo "Interval: ${INTERVAL} seconds"
echo "Trigger Command: ${TRIGGER_CMD}"
echo "=========================================="

cleanup() {
    echo ""
    echo "=========================================="
    echo "Scheduler received shutdown signal"
    echo "Exiting gracefully..."
    echo "=========================================="
    exit 0
}

trap cleanup SIGTERM SIGINT

run_count=0

while true; do
    run_count=$((run_count + 1))

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] Triggering ${TASK_NAME}..."

    if eval "${TRIGGER_CMD}" 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] ✓ Task completed successfully"
    else
        exit_code=$?
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] ✗ Task failed with exit code ${exit_code}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_count}] Will retry after ${INTERVAL} seconds"
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sleeping for ${INTERVAL} seconds..."
    echo ""

    sleep "${INTERVAL}" &
    wait $!
done
