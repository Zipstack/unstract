#!/usr/bin/env bash

# 'src' layout is detected from pdm settings in pyproject.toml
.venv/bin/gunicorn \
    --bind 0.0.0.0:5002 \
    --workers 2 \
    --threads 2 \
    --worker-class gevent\
    --log-level debug \
    --timeout 900 \
    --access-logfile - \
    unstract.runner.main:app
