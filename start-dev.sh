#!/bin/bash

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    cd docker

    # Stop services gracefully
    docker compose -f docker-compose.yaml -f docker-compose-dev-essentials.yaml -f compose.override.yaml down

    # Ensure x2text-service is also stopped if it was started
    docker compose stop x2text-service 2>/dev/null || true
    docker compose rm -f x2text-service 2>/dev/null || true

    cd ..
    echo "✅ All services stopped"
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM

# Check for debug parameter
DEBUG_MODE=false
if [[ "$1" == "debug" ]]; then
    DEBUG_MODE=true
fi

# Set VERSION for builds
export VERSION=latest

if [[ "$DEBUG_MODE" == "true" ]]; then
    echo "🚀 Starting Unstract Development Environment with Debugger Support"
else
    echo "🚀 Starting Unstract Development Environment (Watch Mode Only)"
fi
echo "=================================================="

# Ensure PostHog is disabled for development
echo "🔧 Configuring frontend environment..."
if ! grep -q "REACT_APP_ENABLE_POSTHOG=false" frontend/.env; then
    echo "REACT_APP_ENABLE_POSTHOG=false" >> frontend/.env
    echo "   ✓ PostHog analytics disabled"
fi

# Configure compose override based on debug mode
if [[ "$DEBUG_MODE" == "true" ]]; then
    echo "🔧 Enabling debugger configuration..."
    # Use compose.override.yaml with debugger settings
    cat > docker/compose.override.yaml << 'EOF'
# Refer https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
# Minimize celery workers to reduce memory usage of Unstract (aids development)
services:
  worker:
    command: "-A backend worker --loglevel=info -Q celery,celery_api_deployments,celery_periodic_logs,celery_log_task_queue,file_processing,api_file_processing,file_processing_callback,api_file_processing_callback --autoscale=${WORKER_AUTOSCALE}"

  worker-logging:
    profiles:
      - high_memory

  worker-file-processing:
    profiles:
      - high_memory

  worker-file-processing-callback:
    profiles:
      - high_memory

# Watch configuration
# Refer https://docs.docker.com/compose/how-tos/file-watch/
  frontend:
    build:
      dockerfile: docker/dockerfiles/frontend.Dockerfile
      context: ..
      target: development
    env_file:
      - ../frontend/.env
    develop:
      watch:
      # Sync the frontend directory with the container
      - action: sync
        path: ../frontend/
        target: /app
        ignore: node_modules/
      # Rebuild when dependencies change
      - action: rebuild
        path: ../frontend/package-lock.json
      - action: rebuild
        path: ../frontend/package.json

  backend:
    build:
      dockerfile: docker/dockerfiles/backend.Dockerfile
      context: ..
    ports:
      - "5678:5678"
    labels:
      - traefik.http.services.backend.loadbalancer.server.port=8000
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python manage.py migrate && \
      python manage.py collectstatic --noinput && \
      python -m debugpy --listen 0.0.0.0:5678 .venv/bin/gunicorn \
        --bind 0.0.0.0:8000 \
        --workers 1 \
        --threads 1 \
        --worker-class sync \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 backend.wsgi:application"
    ]
    develop:
      watch:
      # Sync the backend directory with the container
      - action: sync
        path: ../backend/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      - action: sync
        path: ../unstract/
        target: /unstract
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ./dockerfiles/*
      - action: rebuild
        path: ../backend/uv.lock
    ## Uncomment below lines to use local version of unstract-sdk
    ## NOTE: Restart the containers on code change though
    # environment:
    #   - PYTHONPATH=/unstract-sdk/src
    # volumes:
    #   - <path_to_unstract_sdk>/unstract-sdk:/unstract-sdk

  runner:
    build:
      dockerfile: docker/dockerfiles/runner.Dockerfile
      context: ..
    ports:
      - "5681:5681"
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python -m debugpy --listen 0.0.0.0:5681 .venv/bin/gunicorn \
        --bind 0.0.0.0:5002 \
        --workers 1 \
        --threads 1 \
        --worker-class sync \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.runner:app"
    ]
    develop:
      watch:
      # Sync the runner directory with the container
      - action: sync
        path: ../runner/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../runner/uv.lock

  platform-service:
    build:
      dockerfile: docker/dockerfiles/platform.Dockerfile
      context: ..
    ports:
      - "5679:5679"
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python -m debugpy --listen 0.0.0.0:5679 .venv/bin/gunicorn \
        --bind 0.0.0.0:3001 \
        --workers 1 \
        --threads 1 \
        --worker-class sync \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.platform_service.run:app"
    ]
    develop:
      watch:
      # Sync the platform-service directory with the container
      - action: sync
        path: ../platform-service/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../platform-service/uv.lock

  prompt-service:
    build:
      dockerfile: docker/dockerfiles/prompt.Dockerfile
      context: ..
    ports:
      - "5680:5680"
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python -m debugpy --listen 0.0.0.0:5680 .venv/bin/gunicorn \
        --bind 0.0.0.0:3003 \
        --workers 1 \
        --threads 1 \
        --worker-class sync \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.prompt_service.run:app"
    ]
    develop:
      watch:
      # Sync the prompt-service directory with the container
      - action: sync
        path: ../prompt-service/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../prompt-service/uv.lock

  x2text-service:
    build:
      dockerfile: docker/dockerfiles/x2text.Dockerfile
      context: ..
    ports:
      - "5682:5682"
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python -m debugpy --listen 0.0.0.0:5682 .venv/bin/gunicorn \
        --bind 0.0.0.0:3004 \
        --workers 1 \
        --threads 1 \
        --worker-class sync \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.x2text_service.run:app"
    ]
    develop:
      watch:
      # Sync the x2text-service directory with the container
      - action: sync
        path: ../x2text-service/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../x2text-service/uv.lock
EOF
else
    echo "🔧 Using watch mode only (no debugger)..."
    # Use compose.override.yaml without debugger
    cat > docker/compose.override.yaml << 'EOF'
# Refer https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/
# Minimize celery workers to reduce memory usage of Unstract (aids development)
services:
  worker:
    command: "-A backend worker --loglevel=info -Q celery,celery_api_deployments,celery_periodic_logs,celery_log_task_queue,file_processing,api_file_processing,file_processing_callback,api_file_processing_callback --autoscale=${WORKER_AUTOSCALE}"

  worker-logging:
    profiles:
      - high_memory

  worker-file-processing:
    profiles:
      - high_memory

  worker-file-processing-callback:
    profiles:
      - high_memory

# Watch configuration
# Refer https://docs.docker.com/compose/how-tos/file-watch/
  frontend:
    build:
      dockerfile: docker/dockerfiles/frontend.Dockerfile
      context: ..
      target: development
    env_file:
      - ../frontend/.env
    develop:
      watch:
      # Sync the frontend directory with the container
      - action: sync
        path: ../frontend/
        target: /app
        ignore: node_modules/
      # Rebuild when dependencies change
      - action: rebuild
        path: ../frontend/package-lock.json
      - action: rebuild
        path: ../frontend/package.json

  backend:
    build:
      dockerfile: docker/dockerfiles/backend.Dockerfile
      context: ..
    labels:
      - traefik.http.services.backend.loadbalancer.server.port=8000
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      python manage.py migrate && \
      python manage.py collectstatic --noinput && \
      .venv/bin/gunicorn \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        --threads 4 \
        --worker-class gthread \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 backend.wsgi:application"
    ]
    develop:
      watch:
      # Sync the backend directory with the container
      - action: sync
        path: ../backend/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      - action: sync
        path: ../unstract/
        target: /unstract
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ./dockerfiles/*
      - action: rebuild
        path: ../backend/uv.lock

  prompt-service:
    build:
      dockerfile: docker/dockerfiles/prompt.Dockerfile
      context: ..
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      .venv/bin/gunicorn \
        --bind 0.0.0.0:3003 \
        --workers 2 \
        --threads 2 \
        --worker-class gthread \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.prompt_service.run:app"
    ]
    develop:
      watch:
      # Sync the prompt-service directory with the container
      - action: sync
        path: ../prompt-service/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../prompt-service/uv.lock

  x2text-service:
    build:
      dockerfile: docker/dockerfiles/x2text.Dockerfile
      context: ..
    entrypoint: ["bash", "-c"]
    command: [
      "source .venv/bin/activate && \
      uv sync --all-groups && \
      .venv/bin/gunicorn \
        --bind 0.0.0.0:3004 \
        --workers 2 \
        --threads 2 \
        --worker-class gthread \
        --log-level debug \
        --timeout 900 \
        --access-logfile - \
        --reload --graceful-timeout 5 unstract.x2text_service.run:app"
    ]
    develop:
      watch:
      # Sync the x2text-service directory with the container
      - action: sync
        path: ../x2text-service/
        target: /app
        ignore: [.venv/, __pycache__/, "*.pyc", .pytest_cache/, .mypy_cache/]
      # Rebuild when dependencies change
      - action: rebuild
        path: ../x2text-service/uv.lock
EOF
fi

# Start essential services first
echo "📦 Starting essential services (DB, Redis, RabbitMQ, etc.)..."
cd docker && docker compose -f docker-compose-dev-essentials.yaml -f docker-compose.yaml up -d --no-deps db redis rabbitmq minio reverse-proxy
cd ..

# Wait for database to be ready
echo "🔗 Waiting for database..."
cd docker
until docker compose exec -T db pg_isready -h localhost -p 5432 >/dev/null 2>&1; do
  echo "Database starting..."
  sleep 2
done
echo "✅ Database ready"

# Wait for RabbitMQ to be ready
echo "🔗 Waiting for RabbitMQ..."
until docker compose exec -T rabbitmq rabbitmq-diagnostics ping >/dev/null 2>&1; do
  echo "RabbitMQ is unavailable - sleeping"
  sleep 2
done
echo "✅ RabbitMQ is ready"

# Start all services with watch mode
echo "🔨 Starting backend, prompt-service, frontend, worker, and runner with watch mode..."
export VERSION=latest

# Stop any x2text-service that might be running
echo "🛑 Ensuring x2text-service is stopped..."
docker compose stop x2text-service 2>/dev/null || true
docker compose rm -f x2text-service 2>/dev/null || true

# Start only the services we need, explicitly excluding x2text-service
echo "🚀 Starting selected services..."
docker compose up --watch --no-deps backend prompt-service frontend runner worker platform-service &
cd ..

echo ""
echo "✅ Services are starting up!"
echo ""
echo "📍 Access points:"
echo "   Frontend: http://frontend.unstract.localhost"
echo "   Backend API: http://frontend.unstract.localhost/api/v1"
echo "   Minio Console: http://minio.unstract.localhost"
echo "   RabbitMQ Management: http://localhost:15672 (admin/password)"
echo ""

if [[ "$DEBUG_MODE" == "true" ]]; then
    echo "🐛 Debug Ports (for manual debugger attachment):"
    echo "   Backend: localhost:5678"
    echo "   Prompt Service: localhost:5680"
    echo "   Platform Service: localhost:5679"
    echo "   Runner: localhost:5681"
    echo "   X2Text: localhost:5682"
    echo ""
    echo "📝 Services run with debug logging enabled"
    echo "🔌 To attach debugger, configure it to connect to the appropriate port"
    echo "🌐 Frontend: Use browser DevTools for debugging"
else
    echo "🔄 Watch Mode: File changes will trigger automatic reloads"
    echo "🌐 Debugging: Use browser DevTools for frontend debugging"
fi

echo ""
echo "Usage:"
echo "   ./start-dev.sh        # Start with watch mode only"
echo "   ./start-dev.sh debug  # Start with debugger + watch mode"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for interrupt
wait