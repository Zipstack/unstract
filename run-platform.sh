#!/usr/bin/env bash

set -o nounset # exit if a variable is not set
set -o errexit # exit for any command failure"

# text color escape codes (\033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
red_text='\033[31m'
default_text='\033[39m'

# set -x/xtrace uses PS4 for more info
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
  echo -e "   -h, --help          Displays the help information"
  echo -e "   -e, --only-env      Only do env files setup"
  echo -e "   -p, --only-pull     Only do docker images pull"
  echo -e "   -b, --build-local   Build docker images locally"
  echo -e "   -x, --trace         Enables trace mode"
  echo -e "   -V, --verbose       Print verbose logs"
  echo -e "   -v, --version       Docker images version tag (default \"latest\")"
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
      -p | --only-pull)
        opt_only_pull=true
        ;;
      -b | --build-local)
        opt_build_local=true
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
  debug "OPTION only_pull: $opt_only_pull"
  debug "OPTION build_local: $opt_build_local"
  debug "OPTION verbose: $opt_verbose"
  debug "OPTION version: $opt_version"
}

setup_env() {
  # Generate Fernet Key. Refer https://pypi.org/project/cryptography/. for both backend and platform-service.
  ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
  DEFAULT_AUTH_KEY="unstract"
  
  for service in "${services[@]}"; do
    sample_env_path="$script_dir/$service/sample.env"
    env_path="$script_dir/$service/.env"

    if [ -e "$sample_env_path" ] && [ ! -e "$env_path" ]; then
      cp "$sample_env_path" "$env_path"
      # Add encryption secret for backend and platform-service.
      if [[ "$service" == "backend" || "$service" == "platform-service" ]]; then
        echo -e "$blue_text""Adding encryption secret to $service""$default_text"
        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s/ENCRYPTION_KEY.*/ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"/" $env_path
        else
          sed -i "s/ENCRYPTION_KEY.*/ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"/" $env_path
        fi
      fi
      # Add default auth credentials for backend.
      if [ "$service" == "backend" ]; then
        echo -e "$blue_text""Adding default auth credentials to $service""$default_text"
        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s/DEFAULT_AUTH_USERNAME.*/DEFAULT_AUTH_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          sed -i '' "s/DEFAULT_AUTH_PASSWORD.*/DEFAULT_AUTH_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
        else
          sed -i "s/DEFAULT_AUTH_USERNAME.*/DEFAULT_AUTH_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          sed -i "s/DEFAULT_AUTH_PASSWORD.*/DEFAULT_AUTH_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
        fi
      fi
      echo -e "Created env for ""$blue_text""$service""$default_text" at ""$blue_text""$env_path""$default_text"."
    else
      echo -e "Found existing env for ""$blue_text""$service""$default_text" at ""$blue_text""$env_path""$default_text"."
    fi
  done

  if [ ! -e "$script_dir/docker/essentials.env" ]; then
    cp "$script_dir/docker/sample.essentials.env" "$script_dir/docker/essentials.env"
    echo -e "Created env for ""$blue_text""essential services""$default_text"" at ""$blue_text""$script_dir/docker/essentials.env""$default_text""."
  else
    echo -e "Found existing env for ""$blue_text""essential services""$default_text"" at ""$blue_text""$script_dir/docker/essentials.env""$default_text""."
  fi

  if [ ! -e "$script_dir/docker/proxy_overrides.yaml" ]; then
    echo -e "NOTE: Proxy behaviour can be overridden via ""$blue_text""$script_dir/docker/proxy_overrides.yaml""$default_text""."
  else
    echo -e "Found ""$blue_text""$script_dir/docker/proxy_overrides.yaml""$default_text"". Proxy behaviour will be overridden."
  fi

  if [ "$opt_only_env" = true ]; then
    echo "Done." && exit 0
  fi
}

build_services() {
  pushd ${script_dir}/docker 1>/dev/null

  if [ "$opt_build_local" = true ]; then
    echo "Building docker images locally."
    VERSION=$opt_version docker-compose -f $script_dir/docker/docker-compose.build.yaml build || {
      echo -e "$red_text""Failed to build docker images.""$default_text"
      exit 1
    }
  else
    for service in "${services[@]}"; do
      if ! docker image inspect "unstract/${service}:$opt_version" &> /dev/null; then
        echo -e "$red_text""Docker image 'unstract/${service}:$opt_version' not found. Pulling...""$default_text"
        docker pull unstract/${service}:$opt_version || {
          echo -e "$red_text""Failed to pull 'unstract/${service}:$opt_version'. Check if version exists.""$default_text"
          exit 1
        }
      else
        echo -e "Found docker image ""$blue_text""'unstract/${service}:$opt_version'""$default_text""."
      fi
    done
  fi

  popd 1>/dev/null

  if [ "$opt_only_pull" = true ]; then
    echo "Done." && exit 0
  fi
}

run_services() {
  pushd ${script_dir}/docker 1>/dev/null

  echo -e "$blue_text""Starting docker containers in detached mode""$default_text"
  VERSION=$opt_version docker compose up -d
  echo -e "\nOnce the services are up, visit ""$blue_text""http://frontend.unstract.localhost""$default_text"" in your browser."
  echo "See logs with:"
  echo -e "    ""$blue_text""docker compose -f docker/docker-compose.yaml logs -f""$default_text"

  popd 1>/dev/null
}

#
# Run Unstract platform - BEGIN
#
if ! command -v docker compose &> /dev/null; then
  echo "$red_text""docker compose not found. Please install it and try again.""$default_text"
  exit 1
fi

opt_only_env=false
opt_only_pull=false
opt_build_local=false
opt_verbose=false
opt_version="latest"

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
# Extract service names from docker compose file.
services=($(VERSION=$opt_version docker compose -f $script_dir/docker/docker-compose.build.yaml config --services))

display_banner
parse_args $*

setup_env
build_services
run_services
#
# Run Unstract platform - END
#
