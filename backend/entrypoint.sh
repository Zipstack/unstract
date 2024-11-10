#!/usr/bin/env bash

cmd=$1
if [ "$cmd" = "migrate" ]; then
    echo "Migration initiated"
    .venv/bin/python manage.py migrate
elif [ "$cmd" = "prepare_and_migrate" ]; then
    echo "Creating schema in database"
    .venv/bin/python manage.py create_schema
    echo "Migration initiated"
    .venv/bin/python manage.py migrate
fi

# NOTE: Leaving below for reference incase required in the future
# python manage.py runserver 0.0.0.0:8000 --insecure
# NOTE updated socket threads
.venv/bin/gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --log-level debug \
    --timeout 600 \
    --access-logfile - \
    backend.wsgi:application
