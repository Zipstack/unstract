#!/usr/bin/env bash

set -o nounset # exit if a variable is not set
set -o errexit # exit for any command failure"

# text color escape codes (\033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
green_text='\033[32m'
red_text='\033[31m'
default_text='\033[39m'
yellow_text='\033[33m'

# set -x/xtrace uses PS4 for more info
PS4="$blue_text"'${0}:${LINENO}: '"$default_text"


debug() {
  if [ "$opt_verbose" = true ]; then
    echo $1
  fi
}

check_dependencies() {
  if ! command -v git &> /dev/null; then
    echo "$red_text""git not found. Exiting.""$default_text"
    exit 1
  fi
  if ! command -v python3 &> /dev/null; then
    echo "$red_text""python3 not found. Exiting.""$default_text"
    exit 1
  fi
  if ! command -v docker &> /dev/null; then
    echo "$red_text""docker not found. Exiting.""$default_text"
    exit 1
  fi
  # For 'docker compose' vs 'docker-compose', see https://stackoverflow.com/a/66526176.
  docker compose >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    docker_compose_cmd="docker compose"
  elif command -v docker-compose &> /dev/null; then
    docker_compose_cmd="docker-compose"
  else
    echo "$red_text""Both 'docker compose' and 'docker-compose' not found. Exiting.""$default_text"
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
  printf "Run Unstract platform in docker containers\n"
  echo
  echo -e "Syntax: $0 [options]"
  echo -e "Options:"
  echo -e "   -h, --help          Display help information"
  echo -e "   -e, --only-env      Only do env files setup"
  echo -e "   -p, --only-pull     Only do docker images pull"
  echo -e "   -b, --build-local   Build docker images locally"
  echo -e "   -u, --update        Update services version"
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
      -u | --update)
        opt_update=true
        ;;
      -x | --trace)
        set -o xtrace  # display every line before execution; enables PS4
        ;;
      -V | --verbose)
        opt_verbose=true
        ;;
      -v | --version)
        if [ -z "${2-}" ]; then
          echo "No version specified."
          echo
          display_help
          exit
        else
          opt_version="$2"
        fi
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
  debug "OPTION upgrade: $opt_update"
  debug "OPTION verbose: $opt_verbose"
  debug "OPTION version: $opt_version"
}

do_git_pull() {
  if [ "$opt_update" = false ]; then
    return
  fi

  echo "Fetching release tags."
  current_version=$(git describe --tags --abbrev=0)
  git fetch --quiet --tags

  if [[ "$opt_version" == "latest" ]]; then
    target_branch=`git ls-remote --tags origin | awk -F/ '{print $3}' | sort -V | tail -n1`
  elif [[ "$opt_version" == "current" ]]; then
    target_branch=`git branch --show-current`
    opt_build_local=true
    echo -e "Opting ""$blue_text""local build""$default_text"" of Docker images from ""$blue_text""$target_branch""$default_text"" branch."
  elif [ -z $(git tag -l "$opt_version") ]; then
    echo -e "$red_text""Version not found.""$default_text"
    version_regex="^v([0-9]+)\.([0-9]+)\.([0-9]+)(-[a-zA-Z0-9]+(\.[0-9]+)?)?$"
    if [[ ! $opt_version =~ $version_regex ]]; then
      echo -e "$red_text""Version must be prefixed with 'v' and follow SemVer (e.g. v0.47.0).""$default_text"
    fi
    exit 1
  else
    target_branch="$opt_version"
  fi

  echo -e "Performing ""$blue_text""git checkout""$default_text"" to ""$blue_text""$target_branch""$default_text""."
  git checkout --quiet $target_branch

  echo -e "Performing ""$blue_text""git pull""$default_text"" on ""$blue_text""$target_branch""$default_text""."
  git pull --quiet $(git remote) $target_branch
}

_copy_or_merge_env() {
  local src_file_path="$1"
  local dest_file_path="$2"
  local service="$3"

  if [ -e "$src_file_path" ] && [ ! -e "$dest_file_path" ]; then
    first_setup=true
    cp "$src_file_path" "$dest_file_path"
    echo -e "Created env for ""$blue_text""$service""$default_text"" at ""$blue_text""$dest_file_path""$default_text""."
  elif [ "$opt_only_env" = true ] || [ "$opt_update" = true ]; then
    python3 $script_dir/docker/scripts/merge_env.py "$src_file_path" "$dest_file_path"
    if [ $? -ne 0 ]; then
      exit 1
    fi
    echo -e "Merged env for ""$blue_text""$service""$default_text"" at ""$blue_text""$dest_file_path""$default_text""."
  fi
}

setup_env() {
  # Generate Fernet Key. Refer https://pypi.org/project/cryptography/. for both backend and platform-service.
  ENCRYPTION_KEY=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
  DEFAULT_AUTH_KEY="unstract"

  for service in "${services[@]}"; do
    sample_env_path="$script_dir/$service/sample.env"
    env_path="$script_dir/$service/.env"

    _copy_or_merge_env $sample_env_path $env_path $service

    if [ "$first_setup" = true ]; then
      # Add encryption secret for backend and platform-service.
      if [[ "$service" == "backend" || "$service" == "platform-service" ]]; then
        echo -e "$blue_text""Adding encryption secret to $service""$default_text"
        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s/ENCRYPTION_KEY.*/ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"/" $env_path
        else
          sed -i "s/ENCRYPTION_KEY.*/ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"/" $env_path
        fi
      fi
      # Add default auth and system admin credentials for backend.
      if [ "$service" == "backend" ]; then
        echo -e "$blue_text""Adding default auth and system admin credentials to $service""$default_text"
        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s/DEFAULT_AUTH_USERNAME.*/DEFAULT_AUTH_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          sed -i '' "s/DEFAULT_AUTH_PASSWORD.*/DEFAULT_AUTH_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
          # sed -i '' "s/SYSTEM_ADMIN_USERNAME.*/SYSTEM_ADMIN_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          # sed -i '' "s/SYSTEM_ADMIN_PASSWORD.*/SYSTEM_ADMIN_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
        else
          sed -i "s/DEFAULT_AUTH_USERNAME.*/DEFAULT_AUTH_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          sed -i "s/DEFAULT_AUTH_PASSWORD.*/DEFAULT_AUTH_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
          # sed -i "s/SYSTEM_ADMIN_USERNAME.*/SYSTEM_ADMIN_USERNAME=\"$DEFAULT_AUTH_KEY\"/" $env_path
          # sed -i "s/SYSTEM_ADMIN_PASSWORD.*/SYSTEM_ADMIN_PASSWORD=\"$DEFAULT_AUTH_KEY\"/" $env_path
        fi
      fi
    fi
  done

  _copy_or_merge_env "$script_dir/docker/sample.essentials.env" "$script_dir/docker/essentials.env" "essential services"
  _copy_or_merge_env "$script_dir/docker/sample.env" "$script_dir/docker/.env" "docker compose"

  if [ "$opt_only_env" = true ]; then
    echo -e "$green_text""Done.""$default_text" && exit 0
  fi
}

build_services() {
  pushd ${script_dir}/docker 1>/dev/null

  if [ "$opt_build_local" = true ]; then
    echo -e "$blue_text""Building""$default_text"" docker images tag ""$blue_text""$opt_version""$default_text"" locally."
    VERSION=$opt_version $docker_compose_cmd -f $script_dir/docker/docker-compose.build.yaml build || {
      echo -e "$red_text""Failed to build docker images.""$default_text"
      exit 1
    }
  elif [ "$first_setup" = true ] || [ "$opt_update" = true ]; then
    echo -e "$blue_text""Pulling""$default_text"" docker images tag ""$blue_text""$opt_version""$default_text""."
    # Try again on a slow network.
    VERSION=$opt_version $docker_compose_cmd -f $script_dir/docker/docker-compose.yaml pull ||
    VERSION=$opt_version $docker_compose_cmd -f $script_dir/docker/docker-compose.yaml pull || {
      echo -e "$red_text""Failed to pull docker images.""$default_text"
      echo -e "$red_text""Either version not found or docker is not running.""$default_text"
      echo -e "$red_text""Please check and try again.""$default_text"
      exit 1
    }
  fi

  popd 1>/dev/null

  if [ "$opt_only_pull" = true ]; then
    echo -e "$green_text""Done.""$default_text" && exit 0
  fi
}


run_services() {
  pushd ${script_dir}/docker 1>/dev/null

  echo -e "$blue_text""Starting docker containers in detached mode""$default_text"
  VERSION=$opt_version $docker_compose_cmd up -d

  if [ "$opt_update" = true ]; then
    echo ""
    if [[ "$opt_version" == "main" ]]; then
      echo -e "$green_text""Updated platform to latest main (unstable).""$default_text"
    else
      echo -e "$green_text""Updated platform to $opt_version version.""$default_text"
    fi

    # Show release notes on version update if applicable
    python3 "$script_dir/docker/scripts/release-notes/print_release_notes.py" "$current_version" "$target_branch"
  fi
  echo -e "\nOnce the services are up, visit ""$blue_text""http://frontend.unstract.localhost""$default_text"" in your browser."
  echo -e "\nSee logs with:"
  echo -e "    ""$blue_text""$docker_compose_cmd -f docker/docker-compose.yaml logs -f""$default_text"
  echo -e "Configure services by updating corresponding ""$yellow_text""<service>/.env""$default_text"" files."
  echo -e "Make sure to ""$yellow_text""restart""$default_text"" the services with:"
  echo -e "    ""$blue_text""$docker_compose_cmd -f docker/docker-compose.yaml up -d""$default_text"
  if [ "$first_setup" = true ]; then
    echo -e "\n###################### BACKUP ENCRYPTION KEY ######################"
    echo -e "Copy the value of ""$yellow_text""ENCRYPTION_KEY""$default_text"" in any of the following env files"
    echo -e "to a secure location:\n"
    echo -e "- ""$red_text""backend/.env""$default_text"
    echo -e "- ""$red_text""platform-service/.env""$default_text"
    echo -e "\nAapter credentials are encrypted by the platform using this key."
    echo -e "Its loss or change will make all existing adapters inaccessible!"
    echo -e "###################################################################"
  fi

  popd 1>/dev/null
}

#
# Run Unstract platform - BEGIN
#
check_dependencies

opt_only_env=false
opt_only_pull=false
opt_build_local=false
opt_update=false
opt_verbose=false
opt_version="latest"

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")
first_setup=false
# Extract service names from docker compose file.
services=($(VERSION=$opt_version $docker_compose_cmd -f $script_dir/docker/docker-compose.build.yaml config --services))
current_version=""
target_branch=""

display_banner
parse_args $*

do_git_pull
setup_env
build_services
run_services
#
# Run Unstract platform - END
#
