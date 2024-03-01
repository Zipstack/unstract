#!/usr/bin/env bash

# Run away from anything even a little scary
set -o nounset # -u exit if a variable is not set
set -o errexit # -f exit for any command failure"

# text color escape codes (please note \033 == \e but OSX doesn't respect the \e)
blue_text='\033[94m'
red_text='\033[31m'
default_text='\033[39m'

# set -x/xtrace uses a Sony PS4 for more info
PS4="$blue_text""${0}:${LINENO}: ""$default_text"

############################################################
# Help                                                     #
############################################################
display_help()
{
   # Display Help
   printf "This script will create ENVs and files for running docker compose\n"
   printf "It will also run docker compose up and docker compose build\n"
   echo
   # $0 is the currently running program
   echo -e "Syntax: $0"
   echo -e "options:"
   echo -e "   -v --version     Specifies the version tag for the run platform. (default \"dev\")"
   echo -e "   -b --build       Specifies the version tag for building the Docker image.  (default \"dev\")"
   echo -e "   -c --copy        Only copies environment files without running Docker Compose."
   echo -e "   -h --help        Displays the help information."
   echo -e "   -x --debug       Enables verbose mode."
   echo -e "   -d --background  Runs Docker Compose up in detached mode."
   echo -e ""
}

########## Pointless Banner for street cred ##########
# Make sure the console is huuuge
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

dockerDetachedMode=""

# $0 is the currently running program (this file)
this_file_directory=$(dirname $0)

services_to_process=(
    "backend"
    "frontend"
    "document-service"
    "platform-service"
    "prompt-service"
    "worker"
    "x2text-service"
)


copy_envs()
{
    for service in "${services_to_process[@]}"; do
        sample_env_path="$this_file_directory/$service/sample.env"
        env_path="$this_file_directory/$service/.env"
        # Generate Fernet Key Refer https://pypi.org/project/cryptography/
        ENCRYPTION_KEY=$(python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
        if [ -e "$sample_env_path" ] && [ ! -e "$env_path" ]; then
            cp "$sample_env_path" "$env_path"
             # Need to add encryption secret to env of platform-service and backend
            if [[ "$service" == "backend" || "$service" == "platform-service" ]]; then
              echo "Adding encryption secret to  $service"
              echo "ENCRYPTION_KEY=\"$ENCRYPTION_KEY\"" >> $env_path
            fi
            echo "Copied contents from sample.env to .env in $service"

        else
         echo "$env_path already exists.."
        fi
    done
    if [ ! -e "$this_file_directory/docker/essentials.env" ]; then
        cp "$this_file_directory/docker/sample.essentials.env" "$this_file_directory/docker/essentials.env"
        echo "Copied contents from sample.essentials.env to essentials.env in docker"
    else
        echo "$this_file_directory/docker/essentials.env already exists.."
    fi
    if [ ! -e "$this_file_directory/docker/proxy_overrides.yaml" ]; then
        cp "$this_file_directory/docker/sample.proxy_overrides.yaml" "$this_file_directory/docker/proxy_overrides.yaml"
        echo "Copied contents from sample.proxy_overrides.yaml to proxy_overrides.yaml in docker"
    else
        echo "$this_file_directory/docker/proxy_overrides.yaml already exists.."
    fi
}

run_all_services() {
  ########## Start Docker ##########
  pushd ${this_file_directory}/docker
  echo -e "$blue_text""Starting Docker Compose""$default_text"
  VERSION=$opt_version docker compose up $dockerDetachedMode
  popd
}

build_all_services() {
    pushd ${this_file_directory}/docker

    # Define your Docker compose file
    DOCKER_COMPOSE_FILE="docker-compose.build.yaml"

    # Check if docker-compose is installed
    if ! command -v docker compose &> /dev/null; then
      echo "Error: docker compose is not installed. Please install it and try again."
      exit 1
    fi

    # Extract service names from Docker Compose file
    services=($(VERSION=$opt_version docker compose -f "${DOCKER_COMPOSE_FILE}" config --services))

    # Loop through each service and build it
    for service in "${services[@]}"; do
      # Check if image exists
      if ! docker image inspect "unstract/${service}:$opt_version" &> /dev/null; then
        echo "Docker image 'unstract/${service}' does not exist. Building..."
        VERSION=$opt_version docker-compose -f "${DOCKER_COMPOSE_FILE}" build "${service}" || {
          echo "Error: Building service '${service}' failed."
          exit 1
        }
      else
        echo "Docker image 'unstract/${service}' already exists. Skipping..."
      fi
    done

    echo "All services built or already exist."
    popd
}

while [[ $# -gt 0 ]]; do
        arg="$1"
        case $arg in
            -h | --help)
              display_help
              exit
              ;;
            -v | --version)
              opt_version="$2"
              copy_envs
              build_all_services
              run_all_services
              ;;
            -c | --copy)
              copy_envs
              exit
              ;;
            -b | --build)
              opt_version="$2"
              build_all_services
              exit
              ;;
            -x | debug)
              set -o xtrace  # -x display every line before execution; enables PS4
              ;;
            -d | --background)
              opt_version="$2"
              dockerDetachedMode="-d"
              run_all_services
              ;;
            *)
              echo ""$2" is not a known command."
              echo
              display_help
              exit
              ;;
        esac
done



opt_version="dev"


########## Dependency Check ##########
if ! docker compose version >/dev/null 2>/dev/null; then
  echo -e "$red_text""docker compose v2 not found! please install docker compose!""$default_text"
  exit 1
fi


# $? is the exit code of the last command. So here: docker compose up
if test $? -ne 0; then
  echo -e "$red_text""Docker compose failed.  If you are seeing container conflicts""$default_text"
  echo -e "$red_text""please consider removing old containers""$default_text"
fi

copy_envs
build_all_services
run_all_services

########## Ending Docker ##########
if [ -z "$dockerDetachedMode" ]; then
  VERSION=$opt_version docker compose down
else
  echo -e "$blue_text""Unstract containers are running!""$default_text"
fi
