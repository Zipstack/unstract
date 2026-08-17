#!/usr/bin/env bash

show_help() {
    echo "Usage: ./entrypoint.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --migrate        Perform database migrations before starting the server."
    echo "  --dev            Run Gunicorn in development mode with --reload and reduced graceful timeout (5s)."
    echo "  --help, -h       Show this help message and exit."
}

# Parse arguments
migrate=false
dev=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --migrate) migrate=true ;;
        --dev) dev=true ;;
        --help|-h) show_help; exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

# Perform database migration if --migrate is provided
if [ "$migrate" = true ]; then
    echo "Migration initiated"
    .venv/bin/python manage.py migrate
fi

# Configure Gunicorn based on --dev flag.
# Threads must exceed concurrent browser tabs — each open Socket.IO WebSocket
# holds one thread for its lifetime. The pool spawns threads lazily, so a high
# ceiling is free at idle.
gunicorn_args=(
    --bind 0.0.0.0:8000
    --workers "${GUNICORN_WORKERS:-2}"
    --threads "${GUNICORN_THREADS:-512}"
    --worker-class gthread
    --worker-connections "${GUNICORN_WORKER_CONNECTIONS:-1000}"
    --log-level debug
    --timeout 600
    --access-logfile -
)

if [ "$dev" = true ]; then
    echo "Running in development mode"
    gunicorn_args+=(--reload --graceful-timeout 5)
else
    echo "Running in production mode"
fi

# Start Gunicorn
.venv/bin/gunicorn "${gunicorn_args[@]}" backend.wsgi:application
