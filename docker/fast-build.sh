#!/bin/bash
# Fast build script using BuildKit cache
set -e

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

VERSION=${VERSION:-local}
WORKERS=${1:-"worker-file-processing worker-callback"}

echo "🚀 Fast build with BuildKit cache enabled"
echo "📦 Building workers: $WORKERS"

# Build with cache mount and parallel builds
for worker in $WORKERS; do
    echo "🔨 Building $worker..."
    docker buildx build \
        --cache-from type=local,src=/tmp/.buildx-cache \
        --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max \
        --file dockerfiles/${worker}.Dockerfile \
        --tag unstract/${worker}:${VERSION} \
        --load \
        . &
done

wait

# Move cache
rm -rf /tmp/.buildx-cache
mv /tmp/.buildx-cache-new /tmp/.buildx-cache

echo "✅ Fast build completed!"
