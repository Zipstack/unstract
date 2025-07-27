#!/bin/bash

# Lightweight Workers Deployment Script
# Deploys and manages lightweight Celery workers

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
WORKERS_DIR="$PROJECT_ROOT/unstract/workers"
DOCKER_DIR="$WORKERS_DIR/docker"
ENV_DIR="$DOCKER_DIR/env"

# Default values
ENVIRONMENT="development"
ACTION="deploy"
WORKERS="all"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.workers.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Help function
show_help() {
    cat << EOF
Lightweight Workers Deployment Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -e, --environment ENV    Environment (development|production) [default: development]
    -a, --action ACTION      Action (deploy|stop|restart|status|logs|scale) [default: deploy]
    -w, --workers WORKERS    Workers to manage (all|api|general|file|callback) [default: all]
    -f, --compose-file FILE  Docker compose file path [default: auto-detected]
    -h, --help              Show this help message

ACTIONS:
    deploy      Deploy workers (build and start)
    stop        Stop workers
    restart     Restart workers
    status      Show worker status
    logs        Show worker logs
    scale       Scale workers up/down
    health      Check worker health

EXAMPLES:
    # Deploy all workers in development
    $0 --environment development --action deploy

    # Stop only API deployment workers
    $0 --action stop --workers api

    # Check status of all workers
    $0 --action status

    # Scale general workers
    $0 --action scale --workers general

    # View logs for file processing workers
    $0 --action logs --workers file

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -a|--action)
                ACTION="$2"
                shift 2
                ;;
            -w|--workers)
                WORKERS="$2"
                shift 2
                ;;
            -f|--compose-file)
                COMPOSE_FILE="$2"
                shift 2
                ;;
            -h|--help)
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

# Validate environment
validate_environment() {
    if [[ "$ENVIRONMENT" != "development" && "$ENVIRONMENT" != "production" ]]; then
        log_error "Invalid environment: $ENVIRONMENT. Must be 'development' or 'production'"
        exit 1
    fi

    if [[ ! -f "$ENV_DIR/$ENVIRONMENT.env" ]]; then
        log_error "Environment file not found: $ENV_DIR/$ENVIRONMENT.env"
        exit 1
    fi

    log_info "Using environment: $ENVIRONMENT"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed or not in PATH"
        exit 1
    fi

    # Check compose file
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Docker compose file not found: $COMPOSE_FILE"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Get worker services based on selection
get_worker_services() {
    case $WORKERS in
        "all")
            echo "worker-api-deployment worker-general"
            ;;
        "api")
            echo "worker-api-deployment"
            ;;
        "general")
            echo "worker-general"
            ;;
        "file")
            echo "worker-file-processing"
            ;;
        "callback")
            echo "worker-callback"
            ;;
        *)
            log_error "Invalid workers selection: $WORKERS"
            exit 1
            ;;
    esac
}

# Deploy workers
deploy_workers() {
    log_info "Deploying workers..."

    # Load environment variables
    export $(cat "$ENV_DIR/$ENVIRONMENT.env" | grep -v '^#' | xargs)

    # Get services to deploy
    SERVICES=$(get_worker_services)

    # Build and deploy
    log_info "Building worker images..."
    docker-compose -f "$COMPOSE_FILE" build $SERVICES

    log_info "Starting workers..."
    docker-compose -f "$COMPOSE_FILE" up -d $SERVICES

    # Wait for health checks
    log_info "Waiting for workers to become healthy..."
    sleep 10

    # Check health
    check_worker_health

    log_success "Workers deployed successfully"
}

# Stop workers
stop_workers() {
    log_info "Stopping workers..."

    SERVICES=$(get_worker_services)
    docker-compose -f "$COMPOSE_FILE" stop $SERVICES

    log_success "Workers stopped"
}

# Restart workers
restart_workers() {
    log_info "Restarting workers..."
    stop_workers
    sleep 5
    deploy_workers
}

# Show worker status
show_status() {
    log_info "Worker status:"

    SERVICES=$(get_worker_services)
    docker-compose -f "$COMPOSE_FILE" ps $SERVICES

    echo ""
    log_info "Worker health checks:"
    check_worker_health
}

# Show worker logs
show_logs() {
    log_info "Worker logs:"

    SERVICES=$(get_worker_services)
    docker-compose -f "$COMPOSE_FILE" logs --tail=100 -f $SERVICES
}

# Scale workers
scale_workers() {
    log_info "Scaling workers..."

    case $WORKERS in
        "api")
            read -p "Number of API deployment workers: " scale_count
            docker-compose -f "$COMPOSE_FILE" up -d --scale worker-api-deployment=$scale_count
            ;;
        "general")
            read -p "Number of general workers: " scale_count
            docker-compose -f "$COMPOSE_FILE" up -d --scale worker-general=$scale_count
            ;;
        *)
            log_error "Scaling not supported for: $WORKERS"
            exit 1
            ;;
    esac

    log_success "Workers scaled successfully"
}

# Check worker health
check_worker_health() {
    local health_status=0

    # Check API deployment worker
    if [[ "$WORKERS" == "all" || "$WORKERS" == "api" ]]; then
        if curl -f -s http://localhost:8080/health > /dev/null 2>&1; then
            log_success "API deployment worker: HEALTHY"
        else
            log_error "API deployment worker: UNHEALTHY"
            health_status=1
        fi
    fi

    # Check general worker
    if [[ "$WORKERS" == "all" || "$WORKERS" == "general" ]]; then
        if curl -f -s http://localhost:8081/health > /dev/null 2>&1; then
            log_success "General worker: HEALTHY"
        else
            log_error "General worker: UNHEALTHY"
            health_status=1
        fi
    fi

    # Check file processing worker
    if [[ "$WORKERS" == "all" || "$WORKERS" == "file" ]]; then
        if curl -f -s http://localhost:8082/health > /dev/null 2>&1; then
            log_success "File processing worker: HEALTHY"
        else
            log_error "File processing worker: UNHEALTHY"
            health_status=1
        fi
    fi

    # Check callback worker
    if [[ "$WORKERS" == "all" || "$WORKERS" == "callback" ]]; then
        if curl -f -s http://localhost:8083/health > /dev/null 2>&1; then
            log_success "Callback worker: HEALTHY"
        else
            log_error "Callback worker: UNHEALTHY"
            health_status=1
        fi
    fi

    return $health_status
}

# Create network if it doesn't exist
create_network() {
    if ! docker network ls | grep -q "unstract_network"; then
        log_info "Creating Docker network: unstract_network"
        docker network create unstract_network
    fi
}

# Main execution
main() {
    log_info "Unstract Lightweight Workers Deployment Script"
    log_info "============================================"

    parse_args "$@"
    validate_environment
    check_prerequisites
    create_network

    case $ACTION in
        "deploy")
            deploy_workers
            ;;
        "stop")
            stop_workers
            ;;
        "restart")
            restart_workers
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs
            ;;
        "scale")
            scale_workers
            ;;
        "health")
            check_worker_health
            ;;
        *)
            log_error "Invalid action: $ACTION"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
