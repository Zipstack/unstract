#!/bin/bash

# SIGTERM handler - acknowledge but don't forward to Python
# This allows graceful shutdown by letting the log processor
# complete naturally via sentinel-based detection
sigterm_handler() {
  echo "SIGTERM received in sidecar shell but ignoring - continuing" >> /shared/logs/logs.txt
}
trap sigterm_handler TERM

# Activate virtual environment
. /app/.venv/bin/activate

# Run the application directly
# Note: removed 'exec' to allow SIGTERM trap to fire
python -m unstract.tool_sidecar.log_processor
