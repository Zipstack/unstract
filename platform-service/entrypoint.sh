#!/usr/bin/env bash

.venv/bin/gunicorn \
    --bind 0.0.0.0:3001 \
    --workers 2 \
    --threads 2 \
    --log-level debug \
    --timeout 900 \
    --access-logfile - \
    unstract.platform_service.run:app
