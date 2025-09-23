#!/bin/bash

# Helper script to run all Unstract workers concurrently
# Usage: ./run-all-workers.sh

echo "Starting all Unstract workers..."

# Array of worker commands with unique node names
declare -a workers=(
    "poe worker --hostname=worker-default@%h"
    "poe worker-logging --hostname=worker-logging@%h"
    "poe worker-api-deployment --hostname=worker-api-deployment@%h"
    "poe worker-file-processing --hostname=worker-file-processing@%h"
    "poe worker-api-file-processing --hostname=worker-api-file-processing@%h"
    "poe worker-file-processing-callback --hostname=worker-file-processing-callback@%h"
    "poe worker-api-file-processing-callback --hostname=worker-api-file-processing-callback@%h"
)

# Array to store background process PIDs
declare -a pids=()

# Function to kill all workers on script exit
cleanup() {
    echo "Stopping all workers..."
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
        fi
    done
    exit 0
}

# Set up trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

# Start each worker in background
for worker in "${workers[@]}"; do
    echo "Starting: $worker"
    $worker &
    pids+=($!)
done

echo "All workers started. PIDs: ${pids[*]}"
echo "Press Ctrl+C to stop all workers"

# Wait for all background processes
wait