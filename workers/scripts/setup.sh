#!/bin/bash

# Worker Setup Script
# Initial setup and configuration for Unstract workers

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
WORKERS_DIR="$PROJECT_ROOT/unstract/workers"
DOCKER_DIR="$WORKERS_DIR/docker"
ENV_DIR="$DOCKER_DIR/env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << EOF
Worker Setup Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --environment ENV    Environment to setup (development|production) [default: development]
    --skip-deps         Skip dependency installation
    --skip-env          Skip environment file creation
    --help              Show this help message

ACTIONS:
    This script will:
    1. Check system requirements
    2. Install required dependencies
    3. Create environment files
    4. Setup Docker network
    5. Build worker images
    6. Verify setup

EOF
}

check_system_requirements() {
    log_info "Checking system requirements..."

    local requirements_met=true

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        requirements_met=false
    else
        log_success "Docker found: $(docker --version)"
    fi

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        requirements_met=false
    else
        if command -v docker-compose &> /dev/null; then
            log_success "Docker Compose found: $(docker-compose --version)"
        else
            log_success "Docker Compose found: $(docker compose version)"
        fi
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        requirements_met=false
    else
        log_success "Python found: $(python3 --version)"
    fi

    # Check uv
    if ! command -v uv &> /dev/null; then
        log_warning "uv not found, will install dependencies with pip"
    else
        log_success "uv found: $(uv --version)"
    fi

    # Check available disk space (minimum 2GB)
    local available_space=$(df "$WORKERS_DIR" | awk 'NR==2 {print $4}')
    local min_space=$((2 * 1024 * 1024))  # 2GB in KB

    if [[ $available_space -lt $min_space ]]; then
        log_error "Insufficient disk space. Available: $(($available_space / 1024 / 1024))GB, Required: 2GB"
        requirements_met=false
    else
        log_success "Sufficient disk space available: $(($available_space / 1024 / 1024))GB"
    fi

    if [[ "$requirements_met" == false ]]; then
        log_error "System requirements not met. Please install missing dependencies."
        exit 1
    fi
}

install_dependencies() {
    if [[ "$SKIP_DEPS" == true ]]; then
        log_info "Skipping dependency installation"
        return
    fi

    log_info "Installing dependencies..."

    # Install Python dependencies for each worker
    local workers=("api-deployment" "general" "file-processing" "callback" "shared")

    for worker in "${workers[@]}"; do
        local worker_dir="$WORKERS_DIR/$worker"

        if [[ ! -d "$worker_dir" ]]; then
            if [[ "$worker" == "file-processing" ]]; then
                worker_dir="$WORKERS_DIR/file_processing"
            else
                continue
            fi
        fi

        if [[ -f "$worker_dir/pyproject.toml" ]]; then
            log_info "Installing dependencies for $worker worker..."

            cd "$worker_dir"

            if command -v uv &> /dev/null; then
                uv sync --frozen 2>/dev/null || {
                    log_warning "uv sync failed for $worker, trying uv install..."
                    uv venv --python python3.11 2>/dev/null || true
                    source .venv/bin/activate 2>/dev/null || true
                    uv pip install -e . 2>/dev/null || log_warning "Failed to install $worker dependencies with uv"
                }
            else
                log_warning "Using pip for $worker (uv not available)"
                pip3 install -e . 2>/dev/null || log_warning "Failed to install $worker dependencies with pip"
            fi

            log_success "Dependencies installed for $worker"
        fi
    done

    cd "$WORKERS_DIR"
}

create_environment_files() {
    if [[ "$SKIP_ENV" == true ]]; then
        log_info "Skipping environment file creation"
        return
    fi

    log_info "Creating environment files..."

    # Create env directory if it doesn't exist
    mkdir -p "$ENV_DIR"

    # Development environment
    if [[ ! -f "$ENV_DIR/development.env" ]]; then
        log_info "Creating development environment file..."
        cat > "$ENV_DIR/development.env" << 'EOF'
# Development Environment Configuration
# Core Configuration
INTERNAL_SERVICE_API_KEY=dev-internal-api-key-123
DJANGO_APP_BACKEND_URL=http://localhost:8000
CELERY_BROKER_URL=amqp://admin:admin123@localhost:5672//

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=unstract_db
DB_USER=unstract_dev
DB_PASSWORD=unstract_pass123

# Worker Configuration
LOG_LEVEL=INFO
API_TIMEOUT=30
MAX_CONCURRENT_TASKS=5
API_RETRY_ATTEMPTS=3
API_RETRY_BACKOFF_FACTOR=2.0

# Celery Configuration
CELERY_WORKER_PREFETCH_MULTIPLIER=1
CELERY_TASK_ACKS_LATE=true
CELERY_WORKER_MAX_TASKS_PER_CHILD=1000

# Runner Service Configuration
UNSTRACT_RUNNER_HOST=http://localhost
UNSTRACT_RUNNER_PORT=5002
UNSTRACT_RUNNER_API_TIMEOUT=120
UNSTRACT_RUNNER_API_RETRY_COUNT=5
UNSTRACT_RUNNER_API_BACKOFF_FACTOR=3

# Monitoring Configuration
FLOWER_USER=admin
FLOWER_PASSWORD=admin123
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin123
EOF
        log_success "Development environment file created"
    else
        log_info "Development environment file already exists"
    fi

    # Production environment
    if [[ ! -f "$ENV_DIR/production.env" ]]; then
        log_info "Creating production environment template..."
        cat > "$ENV_DIR/production.env" << 'EOF'
# Production Environment Configuration
# IMPORTANT: Update all passwords and API keys before deployment!

# Core Configuration
INTERNAL_SERVICE_API_KEY=CHANGE_ME_PRODUCTION_API_KEY
DJANGO_APP_BACKEND_URL=http://backend:8000
CELERY_BROKER_URL=amqp://unstract_user:CHANGE_ME_PASSWORD@rabbitmq:5672//

# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_NAME=unstract_production
DB_USER=unstract_prod
DB_PASSWORD=CHANGE_ME_DB_PASSWORD

# Worker Configuration
LOG_LEVEL=WARNING
API_TIMEOUT=60
MAX_CONCURRENT_TASKS=10
API_RETRY_ATTEMPTS=5
API_RETRY_BACKOFF_FACTOR=2.0

# Celery Configuration
CELERY_WORKER_PREFETCH_MULTIPLIER=1
CELERY_TASK_ACKS_LATE=true
CELERY_WORKER_MAX_TASKS_PER_CHILD=500

# Runner Service Configuration
UNSTRACT_RUNNER_HOST=http://runner
UNSTRACT_RUNNER_PORT=5002
UNSTRACT_RUNNER_API_TIMEOUT=300
UNSTRACT_RUNNER_API_RETRY_COUNT=10
UNSTRACT_RUNNER_API_BACKOFF_FACTOR=2

# Monitoring Configuration
FLOWER_USER=admin
FLOWER_PASSWORD=CHANGE_ME_FLOWER_PASSWORD
GRAFANA_USER=admin
GRAFANA_PASSWORD=CHANGE_ME_GRAFANA_PASSWORD
EOF
        log_warning "Production environment template created - UPDATE PASSWORDS BEFORE USE!"
    else
        log_info "Production environment file already exists"
    fi
}

setup_docker_network() {
    log_info "Setting up Docker network..."

    if ! docker network ls | grep -q "unstract_network"; then
        log_info "Creating Docker network: unstract_network"
        docker network create unstract_network
        log_success "Docker network created"
    else
        log_info "Docker network already exists"
    fi
}

build_worker_images() {
    log_info "Building worker Docker images..."

    # Load environment variables
    if [[ -f "$ENV_DIR/$ENVIRONMENT.env" ]]; then
        export $(cat "$ENV_DIR/$ENVIRONMENT.env" | grep -v '^#' | xargs)
    fi

    # Build images
    local compose_file="$DOCKER_DIR/docker-compose.workers.yml"

    if [[ -f "$compose_file" ]]; then
        log_info "Building all worker images..."
        docker-compose -f "$compose_file" build
        log_success "Worker images built successfully"
    else
        log_error "Docker compose file not found: $compose_file"
        exit 1
    fi
}

verify_setup() {
    log_info "Verifying setup..."

    local setup_ok=true

    # Check environment files
    if [[ ! -f "$ENV_DIR/$ENVIRONMENT.env" ]]; then
        log_error "Environment file missing: $ENV_DIR/$ENVIRONMENT.env"
        setup_ok=false
    fi

    # Check Docker network
    if ! docker network ls | grep -q "unstract_network"; then
        log_error "Docker network not found: unstract_network"
        setup_ok=false
    fi

    # Check Docker images
    local expected_images=("unstract-worker-api-deployment" "unstract-worker-general")
    for image in "${expected_images[@]}"; do
        if ! docker images | grep -q "$image"; then
            log_warning "Docker image not found: $image"
        fi
    done

    if [[ "$setup_ok" == true ]]; then
        log_success "Setup verification passed"
    else
        log_error "Setup verification failed"
        exit 1
    fi
}

show_next_steps() {
    cat << EOF

${GREEN}Setup Complete!${NC}

Next steps:
1. Review environment configuration:
   ${BLUE}$ENV_DIR/$ENVIRONMENT.env${NC}

2. Deploy workers:
   ${BLUE}./scripts/deploy.sh --environment $ENVIRONMENT --action deploy${NC}

3. Monitor workers:
   ${BLUE}./scripts/monitor.sh health${NC}

4. View worker logs:
   ${BLUE}./scripts/deploy.sh --action logs${NC}

5. Access monitoring dashboards:
   - Flower: http://localhost:5555
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3001

For more information, see:
   ${BLUE}$WORKERS_DIR/README.md${NC}

EOF
}

parse_args() {
    ENVIRONMENT="development"
    SKIP_DEPS=false
    SKIP_ENV=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --skip-env)
                SKIP_ENV=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

main() {
    log_info "Unstract Workers Setup Script"
    log_info "============================="

    parse_args "$@"

    log_info "Setting up workers for environment: $ENVIRONMENT"

    check_system_requirements
    install_dependencies
    create_environment_files
    setup_docker_network
    build_worker_images
    verify_setup
    show_next_steps

    log_success "Worker setup completed successfully!"
}

main "$@"
