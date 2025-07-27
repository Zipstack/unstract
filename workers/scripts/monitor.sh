#!/bin/bash

# Worker Monitoring Script
# Provides real-time monitoring and alerting for Unstract workers

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
WORKERS_DIR="$PROJECT_ROOT/unstract/workers"

# Default values
MONITOR_INTERVAL=30
ALERT_THRESHOLD=5
OUTPUT_FORMAT="table"
CONTINUOUS=false

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

# Worker queues
declare -A WORKER_QUEUES=(
    ["api-deployment"]="celery_api_deployments"
    ["general"]="celery"
    ["file-processing"]="file_processing,api_file_processing"
    ["callback"]="file_processing_callback,api_file_processing_callback"
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
Worker Monitoring Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -i, --interval SECONDS      Monitor interval in seconds [default: 30]
    -t, --threshold COUNT       Alert threshold for failed health checks [default: 5]
    -f, --format FORMAT         Output format (table|json|prometheus) [default: table]
    -c, --continuous            Run continuously [default: false]
    -h, --help                  Show this help message

ACTIONS:
    health          Check worker health status
    metrics         Show worker metrics
    queues          Show queue status
    resources       Show resource usage
    alerts          Check for alerts
    report          Generate comprehensive report

EXAMPLES:
    # Check health status once
    $0 health

    # Continuous monitoring every 15 seconds
    $0 --continuous --interval 15 health

    # Show metrics in JSON format
    $0 --format json metrics

    # Generate comprehensive report
    $0 report

EOF
}

parse_args() {
    ACTION="health"

    while [[ $# -gt 0 ]]; do
        case $1 in
            -i|--interval)
                MONITOR_INTERVAL="$2"
                shift 2
                ;;
            -t|--threshold)
                ALERT_THRESHOLD="$2"
                shift 2
                ;;
            -f|--format)
                OUTPUT_FORMAT="$2"
                shift 2
                ;;
            -c|--continuous)
                CONTINUOUS=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            health|metrics|queues|resources|alerts|report)
                ACTION="$1"
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

check_worker_health() {
    local worker="$1"
    local endpoint="${WORKER_ENDPOINTS[$worker]}"

    if [[ -z "$endpoint" ]]; then
        echo "unknown"
        return 1
    fi

    if curl -f -s --max-time 5 "$endpoint/health" > /dev/null 2>&1; then
        echo "healthy"
        return 0
    else
        echo "unhealthy"
        return 1
    fi
}

get_worker_metrics() {
    local worker="$1"
    local endpoint="${WORKER_ENDPOINTS[$worker]}"

    if [[ -z "$endpoint" ]]; then
        echo "{}"
        return 1
    fi

    local metrics=$(curl -f -s --max-time 5 "$endpoint/metrics" 2>/dev/null || echo "{}")
    echo "$metrics"
}

get_queue_status() {
    local queue="$1"

    # Use celery inspect to get queue status
    local status=$(celery -A backend inspect active_queues 2>/dev/null | grep -A 10 "$queue" || echo "unknown")
    echo "$status"
}

show_health_status() {
    case $OUTPUT_FORMAT in
        "table")
            show_health_table
            ;;
        "json")
            show_health_json
            ;;
        "prometheus")
            show_health_prometheus
            ;;
        *)
            log_error "Invalid format: $OUTPUT_FORMAT"
            exit 1
            ;;
    esac
}

show_health_table() {
    echo ""
    echo "Worker Health Status - $(date)"
    echo "=========================================="
    printf "%-20s %-10s %-15s %-20s\n" "Worker" "Status" "Response Time" "Last Check"
    echo "----------------------------------------"

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        local start_time=$(date +%s.%N)
        local status=$(check_worker_health "$worker")
        local end_time=$(date +%s.%N)
        local response_time=$(echo "$end_time - $start_time" | bc -l | xargs printf "%.3f")
        local timestamp=$(date "+%H:%M:%S")

        case $status in
            "healthy")
                printf "%-20s ${GREEN}%-10s${NC} %-15s %-20s\n" "$worker" "HEALTHY" "${response_time}s" "$timestamp"
                ;;
            "unhealthy")
                printf "%-20s ${RED}%-10s${NC} %-15s %-20s\n" "$worker" "UNHEALTHY" "${response_time}s" "$timestamp"
                ;;
            *)
                printf "%-20s ${YELLOW}%-10s${NC} %-15s %-20s\n" "$worker" "UNKNOWN" "${response_time}s" "$timestamp"
                ;;
        esac
    done
    echo ""
}

show_health_json() {
    local json_output="{"
    local first=true

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        if [[ "$first" == false ]]; then
            json_output+=","
        fi
        first=false

        local start_time=$(date +%s.%N)
        local status=$(check_worker_health "$worker")
        local end_time=$(date +%s.%N)
        local response_time=$(echo "$end_time - $start_time" | bc -l)
        local timestamp=$(date -Iseconds)

        json_output+="\"$worker\":{\"status\":\"$status\",\"response_time\":$response_time,\"timestamp\":\"$timestamp\"}"
    done

    json_output+="}"
    echo "$json_output" | jq '.' 2>/dev/null || echo "$json_output"
}

show_health_prometheus() {
    echo "# HELP worker_health_status Worker health status (1=healthy, 0=unhealthy)"
    echo "# TYPE worker_health_status gauge"

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        local status=$(check_worker_health "$worker")
        local value=0
        if [[ "$status" == "healthy" ]]; then
            value=1
        fi
        echo "worker_health_status{worker=\"$worker\"} $value"
    done

    echo ""
    echo "# HELP worker_response_time_seconds Worker response time in seconds"
    echo "# TYPE worker_response_time_seconds gauge"

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        local start_time=$(date +%s.%N)
        check_worker_health "$worker" > /dev/null
        local end_time=$(date +%s.%N)
        local response_time=$(echo "$end_time - $start_time" | bc -l)
        echo "worker_response_time_seconds{worker=\"$worker\"} $response_time"
    done
}

show_worker_metrics() {
    echo ""
    echo "Worker Metrics - $(date)"
    echo "========================="

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        echo ""
        echo "--- $worker Worker ---"
        local metrics=$(get_worker_metrics "$worker")

        if [[ "$OUTPUT_FORMAT" == "json" ]]; then
            echo "$metrics" | jq '.' 2>/dev/null || echo "$metrics"
        else
            echo "$metrics"
        fi
    done
}

show_queue_status() {
    echo ""
    echo "Queue Status - $(date)"
    echo "======================"

    for worker in "${!WORKER_QUEUES[@]}"; do
        echo ""
        echo "--- $worker Worker Queues ---"
        local queues="${WORKER_QUEUES[$worker]}"

        IFS=',' read -ra QUEUE_ARRAY <<< "$queues"
        for queue in "${QUEUE_ARRAY[@]}"; do
            echo "Queue: $queue"
            get_queue_status "$queue"
            echo ""
        done
    done
}

show_resource_usage() {
    echo ""
    echo "Worker Resource Usage - $(date)"
    echo "==============================="

    # Get Docker container stats
    local containers=$(docker ps --format "table {{.Names}}" | grep -E "(worker-|unstract-worker)" || true)

    if [[ -n "$containers" ]]; then
        echo ""
        echo "Container Resource Usage:"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" $containers 2>/dev/null || echo "No worker containers found"
    else
        echo "No worker containers found"
    fi
}

check_alerts() {
    echo ""
    echo "Alert Check - $(date)"
    echo "===================="

    local alerts_found=false

    for worker in "${!WORKER_ENDPOINTS[@]}"; do
        local status=$(check_worker_health "$worker")

        if [[ "$status" != "healthy" ]]; then
            log_error "ALERT: Worker $worker is $status"
            alerts_found=true
        fi
    done

    # Check for high memory usage
    local containers=$(docker ps --format "{{.Names}}" | grep -E "(worker-|unstract-worker)" || true)
    if [[ -n "$containers" ]]; then
        while read -r container; do
            local mem_usage=$(docker stats --no-stream --format "{{.MemPerc}}" "$container" 2>/dev/null | sed 's/%//')

            if [[ -n "$mem_usage" && $(echo "$mem_usage > 80" | bc -l) -eq 1 ]]; then
                log_warning "ALERT: High memory usage in $container: ${mem_usage}%"
                alerts_found=true
            fi
        done <<< "$containers"
    fi

    if [[ "$alerts_found" == false ]]; then
        log_success "No alerts found"
    fi
}

generate_report() {
    echo ""
    echo "Comprehensive Worker Report - $(date)"
    echo "====================================="

    show_health_status
    show_worker_metrics
    show_queue_status
    show_resource_usage
    check_alerts
}

run_continuous_monitoring() {
    log_info "Starting continuous monitoring (interval: ${MONITOR_INTERVAL}s)"

    while true; do
        clear
        case $ACTION in
            "health")
                show_health_status
                ;;
            "metrics")
                show_worker_metrics
                ;;
            "queues")
                show_queue_status
                ;;
            "resources")
                show_resource_usage
                ;;
            "alerts")
                check_alerts
                ;;
            "report")
                generate_report
                ;;
        esac

        echo ""
        log_info "Next update in ${MONITOR_INTERVAL}s (Ctrl+C to stop)"
        sleep "$MONITOR_INTERVAL"
    done
}

main() {
    parse_args "$@"

    if [[ "$CONTINUOUS" == true ]]; then
        run_continuous_monitoring
    else
        case $ACTION in
            "health")
                show_health_status
                ;;
            "metrics")
                show_worker_metrics
                ;;
            "queues")
                show_queue_status
                ;;
            "resources")
                show_resource_usage
                ;;
            "alerts")
                check_alerts
                ;;
            "report")
                generate_report
                ;;
            *)
                log_error "Invalid action: $ACTION"
                show_help
                exit 1
                ;;
        esac
    fi
}

main "$@"
