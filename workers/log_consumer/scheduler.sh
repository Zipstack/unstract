#!/usr/bin/env bash
set -uo pipefail
# Note: pipefail without -e — one task's failure must not abort the loop.

# Task 1: log history consumer (existing).
LOG_HISTORY_INTERVAL="${LOG_HISTORY_CONSUMER_INTERVAL:-5}"
DEFAULT_LOG_HISTORY_CMD="/app/.venv/bin/python /app/log_consumer/process_log_history.py"
LOG_HISTORY_CMD="${TASK_TRIGGER_COMMAND:-$DEFAULT_LOG_HISTORY_CMD}"

# Task 2: notification buffer flush (clubbed dispatch).
# Polls on its OWN cadence (NOTIFICATION_BUFFER_POLL_INTERVAL), decoupled from
# the log-history consumer so one env knob doesn't silently govern both tasks.
# The endpoint short-circuits on an empty PENDING set, so frequent polling is
# cheap; the real dispatch cadence is gated by NOTIFICATION_CLUB_INTERVAL on the
# backend (rows precompute flush_after at enqueue time), so this only bounds how
# soon a due group is picked up.
NOTIFICATION_BUFFER_INTERVAL="${NOTIFICATION_BUFFER_POLL_INTERVAL:-10}"
DEFAULT_BUFFER_FLUSH_CMD="/app/.venv/bin/python /app/log_consumer/process_notification_buffer.py"
BUFFER_FLUSH_CMD="${NOTIFICATION_BUFFER_TASK_COMMAND:-$DEFAULT_BUFFER_FLUSH_CMD}"

# Loop wakes at the finer of the two cadences (min, floored at 1s); each task
# fires independently once its own interval has elapsed.
if [[ "${LOG_HISTORY_INTERVAL}" -lt "${NOTIFICATION_BUFFER_INTERVAL}" ]]; then
    BASE_INTERVAL="${LOG_HISTORY_INTERVAL}"
else
    BASE_INTERVAL="${NOTIFICATION_BUFFER_INTERVAL}"
fi
[[ "${BASE_INTERVAL}" -lt 1 ]] && BASE_INTERVAL=1

echo "=========================================="
echo "Log Consumer Scheduler Starting"
echo "=========================================="
echo "Log history interval: ${LOG_HISTORY_INTERVAL}s  |  Buffer flush interval: ${NOTIFICATION_BUFFER_INTERVAL}s"
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
    # $1 = display name, $2 = command, $3 = run number. Returns the command's
    # exit code but never propagates failure — the caller logs it and moves on.
    local task_name="$1"
    local cmd="$2"
    local run_num="$3"
    local exit_code=0
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_num}] Triggering ${task_name}..."
    if eval "${cmd}" 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_num}] ✓ ${task_name} OK"
    else
        exit_code=$?
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Run #${run_num}] ✗ ${task_name} failed with exit code ${exit_code}"
    fi
    return "${exit_code}"
}

run_count=0
# Seed both at 0 so each task fires on the first loop iteration (now ≫ interval).
last_log_run=0
last_buffer_run=0

while true; do
    now=$(date '+%s')

    if [[ $((now - last_log_run)) -ge "${LOG_HISTORY_INTERVAL}" ]]; then
        run_count=$((run_count + 1))
        run_task "process_log_history" "${LOG_HISTORY_CMD}" "${run_count}"
        last_log_run="${now}"
    fi

    if [[ $((now - last_buffer_run)) -ge "${NOTIFICATION_BUFFER_INTERVAL}" ]]; then
        run_count=$((run_count + 1))
        run_task "process_notification_buffer" "${BUFFER_FLUSH_CMD}" "${run_count}"
        last_buffer_run="${now}"
    fi

    # Background sleep + wait so a SIGTERM/SIGINT interrupts promptly (the trap
    # fires, cleanup runs, the script exits) instead of blocking the full tick.
    sleep "${BASE_INTERVAL}" &
    wait $!
done
