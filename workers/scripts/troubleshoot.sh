#!/bin/bash

# Worker Troubleshooting Script
# Diagnoses and fixes common issues with Unstract workers

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
WORKERS_DIR="$PROJECT_ROOT/unstract/workers"
DOCKER_DIR="$WORKERS_DIR/docker"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Worker endpoints
declare -A WORKER_ENDPOINTS=(
    ["api-deployment"]="http://localhost:8080"
    ["general"]="http://localhost:8081"
    ["file-processing"]="http://localhost:8082"
    ["callback"]="http://localhost:8083"
)

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
Worker Troubleshooting Script

USAGE:
    $0 [OPTIONS] [COMMAND]

OPTIONS:
    --worker WORKER     Target specific worker (api|general|file|callback|all) [default: all]
    --fix              Automatically apply fixes where possible
    --verbose          Show detailed output
    --help             Show this help message

COMMANDS:
    diagnose           Run comprehensive diagnostics
    network            Check network connectivity
    dependencies       Check dependencies and packages
    configuration      Validate configuration files
    permissions        Check file and directory permissions
    logs               Analyze worker logs for errors
    performance        Check performance issues
    cleanup            Clean up common issues
    reset              Reset worker state (stops and rebuilds)

EXAMPLES:
    # Run full diagnostics
    $0 diagnose

    # Check network issues for API worker
    $0 --worker api network

    # Auto-fix issues for all workers
    $0 --fix cleanup

    # Reset file processing worker
    $0 --worker file reset

EOF
}

parse_args() {
    TARGET_WORKER="all"
    AUTO_FIX=false
    VERBOSE=false
    COMMAND="diagnose"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --worker)
                TARGET_WORKER="$2"
                shift 2
                ;;
            --fix)
                AUTO_FIX=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            diagnose|network|dependencies|configuration|permissions|logs|performance|cleanup|reset)
                COMMAND="$1"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

verbose_log() {
    if [[ "$VERBOSE" == true ]]; then
        log_info "$1"
    fi
}

check_worker_containers() {
    log_info "Checking worker containers..."

    local issues_found=false
    local containers

    if [[ "$TARGET_WORKER" == "all" ]]; then
        containers=$(docker ps -a --format "{{.Names}}" | grep -E "(worker-|unstract-worker)" || true)
    else
        case $TARGET_WORKER in
            "api")
                containers="unstract-worker-api-deployment"
                ;;
            "general")
                containers="unstract-worker-general"
                ;;
            "file")
                containers="unstract-worker-file-processing"
                ;;
            "callback")
                containers="unstract-worker-callback"
                ;;
            *)
                log_error "Invalid worker: $TARGET_WORKER"
                return 1
                ;;
        esac
    fi

    if [[ -z "$containers" ]]; then
        log_warning "No worker containers found"
        return 1
    fi

    while read -r container; do
        if [[ -n "$container" ]]; then
            local status=$(docker inspect --format="{{.State.Status}}" "$container" 2>/dev/null || echo "not_found")

            case $status in
                "running")
                    log_success "Container $container: running"
                    ;;
                "exited")
                    log_error "Container $container: exited"
                    issues_found=true

                    if [[ "$AUTO_FIX" == true ]]; then
                        log_info "Attempting to restart $container..."
                        docker start "$container" || log_error "Failed to restart $container"
                    fi
                    ;;
                "not_found")
                    log_error "Container $container: not found"
                    issues_found=true
                    ;;
                *)
                    log_warning "Container $container: $status"
                    issues_found=true
                    ;;
            esac
        fi
    done <<< "$containers"

    return $([[ "$issues_found" == false ]])
}

check_network_connectivity() {
    log_info "Checking network connectivity..."

    local issues_found=false

    # Check Docker network
    if ! docker network ls | grep -q "unstract_network"; then
        log_error "Docker network 'unstract_network' not found"
        issues_found=true

        if [[ "$AUTO_FIX" == true ]]; then
            log_info "Creating Docker network..."
            docker network create unstract_network
        fi
    else
        log_success "Docker network exists"
    fi

    # Check worker health endpoints
    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        if [[ "$TARGET_WORKER" != "all" && "$TARGET_WORKER" != "${worker%%-*}" ]]; then
            continue
        fi

        local endpoint="${WORKER_ENDPOINTS[$worker]}"
        verbose_log "Checking $worker endpoint: $endpoint"

        if curl -f -s --max-time 5 "$endpoint/health" > /dev/null 2>&1; then
            log_success "Worker $worker: endpoint accessible"
        else
            log_error "Worker $worker: endpoint not accessible ($endpoint)"
            issues_found=true
        fi
    done

    # Check RabbitMQ connection
    verbose_log "Checking RabbitMQ connection..."
    if nc -z localhost 5672 2>/dev/null; then
        log_success "RabbitMQ: accessible"
    else
        log_error "RabbitMQ: not accessible on localhost:5672"
        issues_found=true
    fi

    # Check PostgreSQL connection
    verbose_log "Checking PostgreSQL connection..."
    if nc -z localhost 5432 2>/dev/null; then
        log_success "PostgreSQL: accessible"
    else
        log_error "PostgreSQL: not accessible on localhost:5432"
        issues_found=true
    fi

    return $([[ "$issues_found" == false ]])
}

check_dependencies() {
    log_info "Checking dependencies..."

    local issues_found=false

    # Check Python dependencies for each worker
    local workers=("api-deployment" "general" "file_processing" "callback")

    for worker in "${workers[@]}"; do
        if [[ "$TARGET_WORKER" != "all" && "$TARGET_WORKER" != "${worker%%-*}" ]]; then
            continue
        fi

        local worker_dir="$WORKERS_DIR/$worker"
        if [[ ! -d "$worker_dir" && "$worker" == "file_processing" ]]; then
            worker_dir="$WORKERS_DIR/file-processing"
        fi

        if [[ -d "$worker_dir" && -f "$worker_dir/pyproject.toml" ]]; then
            verbose_log "Checking dependencies for $worker..."

            cd "$worker_dir"

            # Check if virtual environment exists
            if [[ ! -d ".venv" ]]; then
                log_warning "Virtual environment not found for $worker"
                issues_found=true

                if [[ "$AUTO_FIX" == true ]]; then
                    log_info "Creating virtual environment for $worker..."
                    if command -v uv &> /dev/null; then
                        uv venv --python python3.11
                        uv sync
                    else
                        python3 -m venv .venv
                        source .venv/bin/activate
                        pip install -e .
                    fi
                fi
            else
                log_success "Virtual environment exists for $worker"
            fi
        fi
    done

    cd "$WORKERS_DIR"
    return $([[ "$issues_found" == false ]])
}

check_configuration() {
    log_info "Checking configuration files..."

    local issues_found=false

    # Check environment files
    local env_files=("$DOCKER_DIR/env/development.env" "$DOCKER_DIR/env/production.env")

    for env_file in "${env_files[@]}"; do
        if [[ -f "$env_file" ]]; then
            verbose_log "Checking $env_file..."

            # Check for required variables
            local required_vars=("INTERNAL_SERVICE_API_KEY" "DJANGO_APP_BACKEND_URL" "CELERY_BROKER_URL")

            for var in "${required_vars[@]}"; do
                if ! grep -q "^$var=" "$env_file"; then
                    log_error "Missing required variable $var in $env_file"
                    issues_found=true
                fi
            done

            # Check for default/insecure values
            if grep -q "CHANGE_ME" "$env_file"; then
                log_warning "Default values found in $env_file - update before production use"
            fi
        else
            log_warning "Environment file not found: $env_file"
        fi
    done

    # Check Docker compose file
    local compose_file="$DOCKER_DIR/docker-compose.workers.yml"
    if [[ -f "$compose_file" ]]; then
        verbose_log "Validating Docker compose file..."
        if docker-compose -f "$compose_file" config > /dev/null 2>&1; then
            log_success "Docker compose file is valid"
        else
            log_error "Docker compose file has syntax errors"
            issues_found=true
        fi
    else
        log_error "Docker compose file not found: $compose_file"
        issues_found=true
    fi

    return $([[ "$issues_found" == false ]])
}

check_permissions() {
    log_info "Checking file permissions..."

    local issues_found=false

    # Check script permissions
    local scripts=("$WORKERS_DIR/scripts/deploy.sh" "$WORKERS_DIR/scripts/monitor.sh" "$WORKERS_DIR/run-worker.sh")

    for script in "${scripts[@]}"; do
        if [[ -f "$script" ]]; then
            if [[ ! -x "$script" ]]; then
                log_error "Script not executable: $script"
                issues_found=true

                if [[ "$AUTO_FIX" == true ]]; then
                    log_info "Making script executable: $script"
                    chmod +x "$script"
                fi
            else
                verbose_log "Script executable: $script"
            fi
        fi
    done

    # Check directory permissions
    local dirs=("$WORKERS_DIR" "$DOCKER_DIR" "$WORKERS_DIR/shared")

    for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            if [[ ! -r "$dir" || ! -w "$dir" ]]; then
                log_error "Insufficient permissions for directory: $dir"
                issues_found=true
            else
                verbose_log "Directory permissions OK: $dir"
            fi
        fi
    done

    return $([[ "$issues_found" == false ]])
}

analyze_worker_logs() {
    log_info "Analyzing worker logs..."

    local issues_found=false

    # Get container logs for analysis
    local containers

    if [[ "$TARGET_WORKER" == "all" ]]; then
        containers=$(docker ps --format "{{.Names}}" | grep -E "(worker-|unstract-worker)" || true)
    else
        case $TARGET_WORKER in
            "api")
                containers="unstract-worker-api-deployment"
                ;;
            "general")
                containers="unstract-worker-general"
                ;;
            "file")
                containers="unstract-worker-file-processing"
                ;;
            "callback")
                containers="unstract-worker-callback"
                ;;
        esac
    fi

    if [[ -z "$containers" ]]; then
        log_warning "No running worker containers found"
        return 1
    fi

    while read -r container; do
        if [[ -n "$container" ]]; then
            verbose_log "Analyzing logs for $container..."

            local logs=$(docker logs --tail=100 "$container" 2>&1)

            # Check for common error patterns
            local error_patterns=("ERROR" "CRITICAL" "Failed" "Exception" "Traceback" "Connection refused" "Permission denied")

            for pattern in "${error_patterns[@]}"; do
                local error_count=$(echo "$logs" | grep -c "$pattern" || true)
                if [[ $error_count -gt 0 ]]; then
                    log_error "Found $error_count occurrences of '$pattern' in $container logs"
                    issues_found=true

                    if [[ "$VERBOSE" == true ]]; then
                        echo "$logs" | grep "$pattern" | tail -5
                    fi
                fi
            done

            # Check for health status
            if echo "$logs" | grep -q "ready" || echo "$logs" | grep -q "started"; then
                log_success "Worker $container appears to be running normally"
            fi
        fi
    done <<< "$containers"

    return $([[ "$issues_found" == false ]])
}

check_performance() {
    log_info "Checking performance issues..."

    local issues_found=false

    # Check Docker container resource usage
    local containers=$(docker ps --format "{{.Names}}" | grep -E "(worker-|unstract-worker)" || true)

    if [[ -n "$containers" ]]; then
        while read -r container; do
            if [[ -n "$container" ]]; then
                local stats=$(docker stats --no-stream --format "{{.CPUPerc}} {{.MemPerc}}" "$container" 2>/dev/null || echo "0% 0%")
                local cpu_usage=$(echo "$stats" | awk '{print $1}' | sed 's/%//')
                local mem_usage=$(echo "$stats" | awk '{print $2}' | sed 's/%//')

                verbose_log "Container $container: CPU ${cpu_usage}%, Memory ${mem_usage}%"

                # Check for high resource usage
                if [[ -n "$cpu_usage" && $(echo "$cpu_usage > 80" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                    log_warning "High CPU usage in $container: ${cpu_usage}%"
                    issues_found=true
                fi

                if [[ -n "$mem_usage" && $(echo "$mem_usage > 80" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                    log_warning "High memory usage in $container: ${mem_usage}%"
                    issues_found=true
                fi
            fi
        done <<< "$containers"
    fi

    # Check system resources
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    local cpu_count=$(nproc)

    if [[ -n "$load_avg" && $(echo "$load_avg > $cpu_count" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
        log_warning "High system load: $load_avg (CPUs: $cpu_count)"
        issues_found=true
    fi

    return $([[ "$issues_found" == false ]])
}

cleanup_issues() {
    log_info "Cleaning up common issues..."

    # Clean up stopped containers
    local stopped_containers=$(docker ps -a --filter "status=exited" --format "{{.Names}}" | grep -E "(worker-|unstract-worker)" || true)

    if [[ -n "$stopped_containers" ]]; then
        log_info "Removing stopped worker containers..."
        echo "$stopped_containers" | xargs docker rm 2>/dev/null || true
    fi

    # Clean up dangling images
    local dangling_images=$(docker images -f "dangling=true" -q || true)

    if [[ -n "$dangling_images" ]]; then
        log_info "Removing dangling images..."
        echo "$dangling_images" | xargs docker rmi 2>/dev/null || true
    fi

    # Clean up unused volumes
    log_info "Cleaning up unused volumes..."
    docker volume prune -f 2>/dev/null || true

    # Fix file permissions
    log_info "Fixing script permissions..."
    find "$WORKERS_DIR/scripts" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true

    log_success "Cleanup completed"
}

reset_worker() {
    log_warning "Resetting worker state - this will stop and rebuild workers"

    read -p "Are you sure you want to reset workers? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        log_info "Reset cancelled"
        return
    fi

    local compose_file="$DOCKER_DIR/docker-compose.workers.yml"

    # Stop and remove containers
    log_info "Stopping workers..."
    docker-compose -f "$compose_file" down 2>/dev/null || true

    # Remove images
    log_info "Removing worker images..."
    docker images | grep -E "(unstract-worker|worker-)" | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || true

    # Rebuild
    log_info "Rebuilding workers..."
    docker-compose -f "$compose_file" build

    log_success "Worker reset completed"
}

run_comprehensive_diagnostics() {
    log_info "Running comprehensive diagnostics..."
    echo ""

    local overall_status=true

    # Run all checks
    check_worker_containers || overall_status=false
    echo ""

    check_network_connectivity || overall_status=false
    echo ""

    check_dependencies || overall_status=false
    echo ""

    check_configuration || overall_status=false
    echo ""

    check_permissions || overall_status=false
    echo ""

    analyze_worker_logs || overall_status=false
    echo ""

    check_performance || overall_status=false
    echo ""

    # Summary
    echo "=========================================="
    if [[ "$overall_status" == true ]]; then
        log_success "All diagnostics passed"
    else
        log_error "Issues found during diagnostics"

        if [[ "$AUTO_FIX" == true ]]; then
            echo ""
            log_info "Auto-fix enabled, running cleanup..."
            cleanup_issues
        else
            echo ""
            log_info "Run with --fix to automatically resolve some issues"
            log_info "Or use specific commands to address individual problems"
        fi
    fi
}

main() {
    log_info "Unstract Workers Troubleshooting Script"
    log_info "======================================="

    parse_args "$@"

    case $COMMAND in
        "diagnose")
            run_comprehensive_diagnostics
            ;;
        "network")
            check_network_connectivity
            ;;
        "dependencies")
            check_dependencies
            ;;
        "configuration")
            check_configuration
            ;;
        "permissions")
            check_permissions
            ;;
        "logs")
            analyze_worker_logs
            ;;
        "performance")
            check_performance
            ;;
        "cleanup")
            cleanup_issues
            ;;
        "reset")
            reset_worker
            ;;
        *)
            log_error "Invalid command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
