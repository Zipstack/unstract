#! /bin/bash

export VERSION=test
if [ "$(docker compose -f ../docker-compose.yaml ps -a --filter status=exited | wc -l)" -gt 1 ]; then
    echo "There are exited containers."
    exit 1
fi
