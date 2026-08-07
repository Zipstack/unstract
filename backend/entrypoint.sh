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

    # Backfill PG-scheduler mirror rows for pipeline schedules created before the
    # mirror existed (UN-3796). NOT a migration — an ordinary management command,
    # sequenced after migrate only because pg_periodic_schedule must exist first.
    #
    # --mirror-only: purely additive, writes only pg_periodic_schedule and never a
    # Beat PeriodicTask, so it is safe at any flag state. Ownership hand-over stays
    # an explicit operator action.
    #
    # Runs on EVERY start, not once: schedules created while an older backend was
    # deployed, and rows previously skipped for malformed args, are only picked up by
    # a re-run. It is idempotent (already-mirrored pipelines are skipped), so there
    # is nothing to retire until Celery is decommissioned.
    #
    # Best-effort by design: a mirror failure must never stop the backend from
    # starting. Beat keeps firing everything in that case, which is the safe state.
    echo "PG schedule mirror backfill initiated"
    .venv/bin/python manage.py reconcile_pg_schedules --mirror-only \
        || echo "WARNING: PG schedule mirror backfill failed; continuing startup (schedules stay on Beat)"
fi

# Configure Gunicorn based on --dev flag
gunicorn_args=(
    --bind 0.0.0.0:8000
    --workers 2
    --threads 2
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
