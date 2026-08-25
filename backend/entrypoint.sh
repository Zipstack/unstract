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

    # Converge schedule ownership to whatever PG_SCHEDULER_ENABLED declares (UN-3796)
    # — adopt when on, release back to Beat when off. NOT a migration: an ordinary
    # management command, sequenced after migrate only because pg_periodic_schedule
    # must exist first.
    #
    # READ THIS BEFORE ASSUMING A RESTART IS INERT. This is NOT the earlier
    # `--mirror-only` invocation, and it does NOT leave Beat alone: with
    # PG_SCHEDULER_ENABLED=true it flips pg_owned and DISABLES the Beat PeriodicTask
    # row for every mirrored pipeline. A rolling restart therefore can move schedules
    # off Beat. (A comment here used to describe --mirror-only and state that
    # "ownership hand-over stays an explicit operator action" — it survived the switch
    # to converge_pg_scheduler and told an SRE auditing exactly this question the
    # opposite of the truth.)
    #
    # Running it on every start is what makes the ROLLBACK real: flipping the env var
    # back is enough, with no operator remembering a management command in every
    # environment (on-prem included, where `manage.py` is not something a deploy can
    # reach). Idempotent both ways, and a no-op for rows whose ownership already
    # matches, so a restart that changes nothing writes nothing.
    #
    # PG_SCHEDULER_ADOPT_PERIODICS additionally moves the dashboard_metrics.* rows;
    # it is separate because adopting them needs workerPgMetrics deployed.
    #
    # Best-effort by design: a convergence failure must never stop the backend from
    # starting. Whatever fired the schedules before keeps firing them in that case.
    PERIODICS_FLAG=""
    if [ "$(printf '%s' "${PG_SCHEDULER_ADOPT_PERIODICS:-}" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
        PERIODICS_FLAG="--periodics"
    fi
    echo "PG schedule ownership convergence initiated"
    # shellcheck disable=SC2086  # intentional word-splitting: empty = flag absent
    .venv/bin/python manage.py converge_pg_scheduler $PERIODICS_FLAG \
        || echo "WARNING: PG schedule convergence failed; continuing startup (schedules keep their current firer)"
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
