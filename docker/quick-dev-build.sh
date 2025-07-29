#!/bin/bash
# Quick development build script for workers
# This builds only the essential workers with optimized caching

set -e

VERSION=${VERSION:-local}
WORKERS=${1:-"file-processing callback"}

echo "🚀 Quick development build for workers: $WORKERS"
echo "📦 Using VERSION=$VERSION"

# Build specific workers with parallel processing
if [[ "$WORKERS" == *"file-processing"* ]]; then
    echo "🔨 Building file-processing worker..."
    docker build \
        --file docker/dockerfiles/worker-file-processing.dev.Dockerfile \
        --tag unstract/worker-file-processing:$VERSION \
        --build-arg VERSION=$VERSION \
        --target development \
        ../ &
    PIDS[0]=$!
fi

if [[ "$WORKERS" == *"callback"* ]]; then
    echo "🔨 Building callback worker..."
    docker build \
        --file docker/dockerfiles/worker-callback.Dockerfile \
        --tag unstract/worker-callback:$VERSION \
        --build-arg VERSION=$VERSION \
        ../ &
    PIDS[1]=$!
fi

# Wait for all builds to complete
for pid in ${PIDS[*]}; do
    if [ ! -z "$pid" ]; then
        wait $pid
        echo "✅ Build process $pid completed"
    fi
done

echo "🎉 Quick development build completed!"
echo "💡 To restart workers: VERSION=$VERSION docker compose -f docker-compose.yaml restart worker-file-processing-new worker-callback-new"
