#!/bin/bash
# Activate virtual environment
. /app/.venv/bin/activate

# Run the application with OpenTelemetry instrumentation
opentelemetry-instrument python -m unstract.tool_sidecar.log_processor
