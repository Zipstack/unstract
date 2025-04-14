#!/usr/bin/env bash

set -o nounset # exit if a variable is not set
set -o errexit # exit for any command failure"

# text color escape codes (\033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
green_text='\033[32m'
red_text='\033[31m'
default_text='\033[39m'

# set -x/xtrace uses PS4 for more info
PS4="$blue_text""${0}:${LINENO}: ""$default_text"

debug() {
  if [ "$opt_verbose" = true ]; then
    echo $1
  fi
}

check_dependencies() {
  if ! command -v python3 &> /dev/null; then
    echo "$red_text""python3 not found. Exiting.""$default_text"
    exit 1
  fi
  if ! command -v docker compose &> /dev/null; then
    echo "$red_text""docker not found. Exiting.""$default_text"
    exit 1
  fi
  # For 'docker compose' vs 'docker-compose', see https://stackoverflow.com/a/66526176.
  if command -v docker compose &> /dev/null; then
    docker_compose_cmd="docker compose"
  elif command -v docker-compose &> /dev/null; then
    docker_compose_cmd="docker-compose"
  else
    echo "$red_text""Both 'docker compose' and 'docker-compose' not found. Exiting.""$default_text"
    exit 1
  fi
  if ! command -v uv &> /dev/null; then
    echo "$red_text""uv not found. Exiting.""$default_text"
    exit 1
  fi
}

display_banner() {
  # Make sure the console is huge
  if test $(tput cols) -ge 64; then
    echo " █████   █████"
    echo "░░███   ░░███ "
    echo " ░███    ░███ "
    echo " ░███    ░███ "
    echo " ░███    ░███ "
    echo " ░███    ░███ "
    echo " ░░█████████     >UNSTRACT COMMUNITY EDITION"
    echo "  ░░░░░░░░░   "
    echo ""
    sleep 1
  fi
}

display_help() {
  printf "Dev environment CLI for Unstract platform services\n"
  echo
  echo -e "Syntax: $0 [options] -s service"
  echo -e "Options:"
  echo -e "   -h, --help                      Display help information"
  echo -e "   -e, --setup-venv                Setup venv                      (requires service)"
  echo -e "   -a, --activate-venv             Activate venv                   (requires service)"
  echo -e "   -i, --install-deps              Install dependencies in venv    (requires service)"
  echo -e "   -d, --destroy-venv              Destroy venv                    (requires service)"
  echo -e "   -p, --install-pre-commit-hook   Install Git pre-commit hook"
  echo -e "   -r, --run-pre-commit-hook       Run Git pre-commit hook"
  echo -e "   -f, --force                     Force operation"
  echo -e "   -s, --service                   Service name"
  echo -e "   -x, --trace                     Enables trace mode"
  echo -e "   -V, --verbose                   Print verbose logs"
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
      -e | --setup-venv)
        opt_setup_venv=true
        ;;
      -a | --activate-venv)
        opt_activate_venv=true
        ;;
      -i | --install-deps)
        opt_install_deps=true
        ;;
      -d | --destroy-venv)
        opt_destroy_venv=true
        ;;
      -p | --install-pre-commit-hook)
        opt_install_pre_commit_hook=true
        ;;
      -r | --run-pre-commit-hook)
        opt_run_pre_commit_hook=true
        ;;
      -f | --force)
        opt_force="--force"
        ;;
      -s | --service)
        if [ -z "${2-}" ]; then
          echo "No service specified."
          echo
          display_help
          exit
        else
          opt_service="$2"
        fi
        shift
        ;;
      -x | --trace)
        set -o xtrace  # display every line before execution; enables PS4
        ;;
      -V | --verbose)
        opt_verbose=true
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

  if [ "$opt_install_pre_commit_hook" = false ] && [ "$opt_run_pre_commit_hook" = false ]; then
    if [ "$opt_service" = "" ]; then
        echo "No service specified."
        echo
        display_help
        exit
    fi
    ret=$(echo ${services[@]} | grep -ow "$opt_service" | wc -w)
    if [ $ret -eq 0 ]; then
      echo "Unknown service '$opt_service'."
      echo
      display_help
      exit
    fi
  fi
  if [ "$opt_setup_venv" = false ] && [ "$opt_activate_venv" = false ] &&
    [ "$opt_install_deps" = false ] && [ "$opt_destroy_venv" = false ] &&
    [ "$opt_install_pre_commit_hook" = false ] && [ "$opt_run_pre_commit_hook" = false ]; then
    echo "One of -e,-a,-i,-d,-p,-r options should be specified."
    echo
    display_help
    exit
  fi

  debug "OPTION setup venv: $opt_setup_venv"
  debug "OPTION activate venv: $opt_activate_venv"
  debug "OPTION install deps: $opt_install_deps"
  debug "OPTION destroy venv: $opt_destroy_venv"
  debug "OPTION install pre-commit hook: $opt_install_pre_commit_hook"
  debug "OPTION run pre-commit hook: $opt_run_pre_commit_hook"
  debug "OPTION service: $opt_service"
  debug "OPTION verbose: $opt_verbose"
}

setup_venv() {
  if [ "$opt_setup_venv" = false ]; then
    return
  fi

  pushd ${script_dir}/$opt_service 1>/dev/null

  if [ -e "package.json" ]; then
    echo -e "Nothing to do for ""$blue_text""$opt_service""$default_text"
  elif [ -e "pyproject.toml" ]; then
    echo -e "Setting up ""$blue_text""Python venv""$default_text"" for ""$blue_text""$opt_service""$default_text"
    if [ -e ".venv" ] && [ "$opt_force" = "--force" ]; then
      rm -rf .venv
    fi
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
  fi

  popd 1>/dev/null
}

activate_venv() {
  if [ "$opt_activate_venv" = false ]; then
    return
  fi

  pushd ${script_dir}/$opt_service 1>/dev/null

  if [ -e "package.json" ]; then
    echo -e "Nothing to do for ""$blue_text""$opt_service""$default_text"
  elif [ -e "pyproject.toml" ]; then
    if [ ! -e ".venv" ]; then
      echo -e "venv not found for ""$blue_text""$opt_service""$default_text"". Please run setup first."
      return
    fi
    echo -e "Run the following in a ""$blue_text""new terminal""$default_text"" to activate venv for ""$blue_text""$opt_service""$default_text"":"
    echo ""
    echo "cd ${script_dir}/$opt_service"
    echo "source .venv/bin/activate"
  fi

  popd 1>/dev/null
}

install_deps() {
  if [ "$opt_install_deps" = false ]; then
    return
  fi

  pushd ${script_dir}/$opt_service 1>/dev/null

  if [ -e "package.json" ]; then
    echo -e "Installing dependencies for ""$blue_text""$opt_service""$default_text"
    npm ci
  elif [ -e "pyproject.toml" ]; then
    if [ ! -e ".venv" ]; then
      echo -e "venv not found for ""$blue_text""$opt_service""$default_text"". Please run setup first."
      return
    fi
    echo -e "Installing dependencies in venv for ""$blue_text""$opt_service""$default_text"
    source .venv/bin/activate
    uv pip install -e .
  fi

  popd 1>/dev/null
}

destroy_venv() {
  if [ "$opt_destroy_venv" = false ]; then
    return
  fi

  pushd ${script_dir}/$opt_service 1>/dev/null

  if [ -e "package.json" ]; then
    echo -e "$blue_text""Nothing to do for $opt_service""$default_text"
  elif [ -e "pyproject.toml" ]; then
    if [ ! -e ".venv" ]; then
      echo -e "venv not found for ""$blue_text""$opt_service""$default_text"". Please run setup first."
      return
    fi
    echo -e "Destroying venv for ""$blue_text""$opt_service""$default_text"
    rm -rf .venv
  fi

  popd 1>/dev/null
}

install_pre_commit_hook() {
  if [ "$opt_install_pre_commit_hook" = false ]; then
    return
  fi

  pushd ${script_dir} 1>/dev/null

  echo -e "Installing ""$blue_text""Git pre-commit hook""$default_text"
  if [ -e ".venv" ] && [ "$opt_force" = "--force" ]; then
    rm -rf .venv
  fi
  python3 -m venv .venv
  source .venv/bin/activate
  uv pip install pre-commit
  # Install lint and hook-check-django-migrations dependencies
  if [ -e "pyproject.toml" ]; then
      uv sync --group dev --group hook-check-django-migrations
  fi
  pre-commit install

  popd 1>/dev/null
}

run_pre_commit_hook() {
  if [ "$opt_run_pre_commit_hook" = false ]; then
    return
  fi

  pushd ${script_dir} 1>/dev/null

  if [ ! -e ".venv" ]; then
    echo -e "$blue_text""Git pre-commit hook""$default_text"" not found. Please run install first."
    return
  fi
  source .venv/bin/activate
  pre-commit run

  popd 1>/dev/null
}

#
# Run Unstract platform - BEGIN
#
check_dependencies

opt_setup_venv=false
opt_activate_venv=false
opt_install_deps=false
opt_destroy_venv=false
opt_install_pre_commit_hook=false
opt_run_pre_commit_hook=false
opt_force=""
opt_service=""
opt_verbose=false

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
# Extract service names from docker compose file.
services=($(VERSION="latest" $docker_compose_cmd -f $script_dir/docker/docker-compose.build.yaml config --services))

display_banner
parse_args $*

setup_venv
activate_venv
install_deps
destroy_venv
install_pre_commit_hook
run_pre_commit_hook
#
# Run Unstract platform - END
#
