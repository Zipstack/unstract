#!/bin/bash

display_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -h, --help              Display this help message"
    echo "  -v, --version           Version tag for built Docker images (default \"dev\")"
    echo "                          Ignored if --no-build is specified"
    echo "  -E, --no-setup-env      Do not setup env"
    echo "  -B, --no-build          Do not build Docker images"
    echo "  -l, --local             Deploy in local instead of a Docker container"
    echo "                          Requires --services (accepts only one service)"
    echo "  -s, --services <names>  Deploys the specified services only"
    echo "                          Expects service names as a comma separated list"
    echo "  -V, --verbose           Print verbose logs"
}

debug() {
    if [ "$opt_verbose" = true ]; then
        echo $1
    fi
}

log() {
    echo $1
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        arg="$1"
        case $arg in
            -h|--help)
                display_help
                exit 0
                ;;
            -v|--version)
                opt_version="$2"
                shift
                ;;
            -E|--no-setup-env)
                opt_no_setup_env=true
                ;;
            -l|--local)
                opt_local=true
                ;;
            -s|--services)
                opt_services="$2"
                shift
                ;;
            -V|--verbose)
                opt_verbose=true
                ;;
            *)
                echo "Unknown option: $arg"
                display_help
                exit 1
                ;;
        esac
        shift
    done

    debug "OPTION version: $opt_version"
    debug "OPTION no_setup_env: $opt_no_setup_env"
    debug "OPTION local: $opt_local"
    debug "OPTION services: $opt_services"
    debug "OPTION verbose: $opt_verbose"
}

check_system_requirements() {
    system_requirements=("git" "docker")
    for sr in "${system_requirements[@]}"; do
        command -v $sr >/dev/null 2>&1 || { echo >&2 "$sr is not installed. Exiting."; exit 1; }
    done
}

_deploy_selected_services() {
    debug "Deploying selected services"

    script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
    project_dir="${script_dir}/../.."
    IFS=',' read -r -a deploy_services <<< "$opt_services"

    not_services=("docker" "document_display_service" "tools" "unstract")

    debug "Services to deploy: ${deploy_services[@]}"
    debug "Not services list: ${not_services[@]}"

    for service_path in "$project_dir"/*; do
        if [ ! -d "$service_path" ]; then
            continue
        fi

        service="$(basename "$service_path")"

        # Check if path is included in not services list.
        if [[ $(echo ${not_services[@]} | grep -F -w $service) ]]
        then
            debug "Not a service, skipping: $service"
            continue
        fi

        if [ "${#deploy_services[@]}" -gt 0 ] &&
            ! [[ $(echo ${deploy_services[@]} | grep -F -w $service) ]]
        then
            debug "Service not opted for deploy: $service"
            continue
        fi

        log "Deploying service: $service"
    done
}

_setup_env_all_services() {
    debug "Setting up env for all services"
}

_build_all_services() {
    debug "Building all services"
    VERSION=$opt_version docker compose -f docker-compose.build.yaml build
}

_deploy_all_services() {
    debug "Deploying all services"
    VERSION=$opt_version docker compose -f docker-compose.yaml up -d
}

deploy_services() {
    if [ -n "$opt_services" ]; then
        _deploy_selected_services
    else
        _setup_env_all_services
        _build_all_services
        _deploy_all_services
    fi
}

opt_version="dev"
opt_no_setup_env=false
opt_local=false
opt_services=""
opt_verbose=false

parse_args "$@"
check_system_requirements
deploy_services
