#!/usr/bin/env bash

set -o nounset # exit if a variable is not set
set -o errexit # exit for any command failure"

# text color escape codes (please note \033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
red_text='\033[31m'
default_text='\033[39m'

# set -x/xtrace uses a Sony PS4 for more info
PS4="$blue_text""${0}:${LINENO}: ""$default_text"

debug() {
  if [ "$opt_verbose" = true ]; then
    echo $1
  fi
}

display_banner() {
  # Make sure the console is huge
  if test $(tput cols) -ge 64; then
    # Make it green!
    echo -e "\033[32m"
    echo -e " _    _ _   _  _____ _______ _____            _____ _______"
    echo -e "| |  | | \ | |/ ____|__   __|  __ \     /\   / ____|__   __|"
    echo -e "| |  | |  \| | (___    | |  | |__) |   /  \ | |       | |"
    echo -e "| |  | | .   |\___ \   | |  |  _  /   / /\ \| |       | |"
    echo -e "| |__| | |\  |____) |  | |  | | \ \  / ____ \ |____   | |"
    echo -e " \____/|_| \_|_____/   |_|  |_|  \_\/_/    \_\_____|  |_|"
    echo -e "                                                         "
    # Make it less green
    echo -e "\033[0m"
    sleep 1
  fi
}

display_help() {
  printf "Run Unstract platform in docker containers\n"
  echo
  echo -e "Syntax: $0 [options]"
  echo -e "Options:"
  echo -e "   -h, --help        Displays the help information"
  echo -e "   -e, --only-env    Only do env files setup"
  echo -e "   -b, --only-build  Only do docker images build"
  echo -e "   -d, --detach      Run docker containers in detached mode"
  echo -e "   -x, --trace       Enables trace mode"
  echo -e "   -V, --verbose     Print verbose logs"
  echo -e "   -v, --version     Docker images version tag (default \"dev\")"
  echo -e ""
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    arg="$1"
    case $arg in
      -h | --help)
        display_help
        exit
        ;;
      -e | --only-env)
        opt_only_env=true
        ;;
      -b | --only-build)
        opt_only_build=true
        ;;
      -d | --detach)
        opt_detach="-d"
        ;;
      -x | --trace)
        set -o xtrace  # display every line before execution; enables PS4
        ;;
      -V | --verbose)
        opt_verbose=true
        ;;
      -v | --version)
        opt_version="$2"
        shift
        ;;
      *)
        echo "'$1' is not a known command."
        echo
        display_help
        exit
        ;;
    esac
    shift
  done

  debug "OPTION only_env: $opt_only_env"
  debug "OPTION only_build: $opt_only_build"
  debug "OPTION detach: $opt_detach"
  debug "OPTION verbose: $opt_verbose"
  debug "OPTION version: $opt_version"
}

setup_env() {
  for service in "${services[@]}"; do
    sample_env_path="$script_dir/$service/sample.env"
    env_path="$script_dir/$service/.env"

    # Generate Fernet Key. Refer https://pypi.org/project/cryptography/.
    ENCRYPTION_KEY=$(python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")

    if [ -e "$sample_env_path" ] && [ ! -e "$env_path" ]; then
      cp "$sample_env_path" "$env_path"
      # Add encryption secret for backend and platform-service.
      if [[ "$service" == "backend" || "$service" == "platform-service" ]]; then
        echo "Adding encryption secret to $service"
        echo "ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"" >> $env_path
      fi
    fi
    echo "Created env for $service at $env_path."
  done

  if [ ! -e "$script_dir/docker/essentials.env" ]; then
    cp "$script_dir/docker/sample.essentials.env" "$script_dir/docker/essentials.env"
  fi
  echo "Created env for essential services at $script_dir/docker/essentials.env."

  if [ ! -e "$script_dir/docker/proxy_overrides.yaml" ]; then
    echo "NOTE: Proxy behaviour can be overridden via $script_dir/docker/proxy_overrides.yaml."
  else
    echo "Found $script_dir/docker/proxy_overrides.yaml. Proxy behaviour will be overridden."
  fi
}

build_services() {
  pushd ${script_dir}/docker 1>/dev/null

  for service in "${services[@]}"; do
    if ! docker image inspect "unstract/${service}:$opt_version" &> /dev/null; then
      echo "Docker image 'unstract/${service}:$opt_version' not found. Building..."
      VERSION=$opt_version docker-compose -f "${DOCKER_COMPOSE_FILE}" build "${service}" || {
        echo "Failed to build docker image for '${service}'."
        exit 1
      }
      echo "Built docker image 'unstract/${service}:$opt_version'."
    else
      echo "Found existing docker image 'unstract/${service}:$opt_version'."
    fi
  done

  popd 1>/dev/null
}

run_services() {
  pushd ${script_dir}/docker 1>/dev/null

  if [ -z "$opt_detach" ]; then
    echo -e "$blue_text""Starting docker containers""$default_text"
  else
    echo -e "$blue_text""Starting docker containers in detach mode""$default_text"
  fi
  VERSION=$opt_version docker compose up $opt_detach

  popd 1>/dev/null
}

if ! command -v docker compose &> /dev/null; then
  echo "docker compose not found. Please install it and try again."
  exit 1
fi

opt_only_env=false
opt_only_build=false
opt_detach=""
opt_verbose=false
opt_version="dev"

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
# Extract service names from docker compose file.
services=($(VERSION=$opt_version docker compose -f $script_dir/docker/docker-compose.build.yaml config --services))

display_banner
parse_args $*

setup_env
if [ "$opt_only_env" = true ]; then
  exit 0
fi
build_services
if [ "$opt_only_build" = true ]; then
  exit 0
fi
run_services
