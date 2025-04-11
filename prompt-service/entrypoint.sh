#!/usr/bin/env bash

# 'src' layout is detected from uv settings in pyproject.toml
.venv/bin/gunicorn \
    --bind 0.0.0.0:3003 \
    --workers 2 \
    --threads 2 \
    --log-level debug \
    --timeout 900 \
    --access-logfile - \
    unstract.prompt_service.run:app
