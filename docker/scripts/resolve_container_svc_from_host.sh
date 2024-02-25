#! /bin/bash

# Inspect Unstract Docker network and add/remove container services
# found to/from local DNS hosts file.
#
# Usage:
#   resolve_container_svc_from_host.sh enable|disable
#
# TODO
# Listen for docker events and automatically update local DNS hosts file.
#
DOCKER_NETWORK=unstract-network
LOCAL_DNS_HOSTS_FILE=/etc/hosts
RECORDS_BEGINNING_MARKER="# DO NOT EDIT -- Unstract containers -- BEGIN"
RECORDS_END_MARKER="# DO NOT EDIT -- Unstract containers -- END"

if [[ "$EUID" -ne 0 ]]; then
    echo "Please run with sudo. Exiting."
    exit 1
fi
if ! command -v docker &> /dev/null
then
    echo "docker is not installed. Exiting."
    exit 2
fi
if ! command -v jq &> /dev/null
then
    echo "jq is not installed. Exiting."
    exit 2
fi

cmd=$1
case $cmd in
  "enable")
    echo "Adding container service IPs to $LOCAL_DNS_HOSTS_FILE..."

    grep -Fxq "$RECORDS_BEGINNING_MARKER" $LOCAL_DNS_HOSTS_FILE
    if [ $? -eq 0 ]; then
        echo "Container service IPs already present. Exiting."
        exit 3
    fi
    grep -Fxq "$RECORDS_END_MARKER" $LOCAL_DNS_HOSTS_FILE
    if [ $? -eq 0 ]; then
        echo "Container service IPs already present. Exiting."
        exit 3
    fi

    network=`docker inspect $DOCKER_NETWORK`
    if [ $? -ne 0 ]; then
        echo "Please run 'docker compose -f docker-compose.yaml up -d' first."
        exit 4
    fi

    records="$RECORDS_BEGINNING_MARKER\n"
    records_str=$(echo $network | jq -r '.[0].Containers[] | "\(.IPv4Address | split("/")[0])  \(.Name),"')
    IFS=',' readarray -t records_arr <<<"$records_str"
    for record in "${records_arr[@]}"
    do
        #TODO Preserve exact middle whitespaces from jq output.
        r=$(echo $record | tr -d ,)
        records+="${r}\n"
    done
    records+="$RECORDS_END_MARKER"

    echo -e $records >> $LOCAL_DNS_HOSTS_FILE

    echo "Done."
    echo ""
    echo "## "
    echo "## IMPORTANT!"
    echo "## For each docker compose up/down, the container IPs can change."
    echo "## Please run this script again to correctly resolve new container"
    echo "## services IPs from docker host."
    echo "## "
    ;;

  "disable")
    echo "Removing container service IPs from $LOCAL_DNS_HOSTS_FILE..."

    grep -Fxq "$RECORDS_BEGINNING_MARKER" $LOCAL_DNS_HOSTS_FILE
    if [ $? -ne 0 ]; then
        echo "Container service IPs not found. Exiting."
        exit 3
    fi
    grep -Fxq "$RECORDS_END_MARKER" $LOCAL_DNS_HOSTS_FILE
    if [ $? -ne 0 ]; then
        echo "Container service IPs not found. Exiting."
        exit 3
    fi

    t=$(date +%s)
    beg_line_no=`awk "/$RECORDS_BEGINNING_MARKER/{ print NR; exit }" $LOCAL_DNS_HOSTS_FILE`
    end_line_no=`awk "/$RECORDS_END_MARKER/{ print NR; exit }" $LOCAL_DNS_HOSTS_FILE`

    echo "Backing up $LOCAL_DNS_HOSTS_FILE to $LOCAL_DNS_HOSTS_FILE.bak.$t."

    if [ "$(uname)" == "Darwin" ]; then
        sed -i.bak.$t '' -e "${beg_line_no},${end_line_no}d" $LOCAL_DNS_HOSTS_FILE
    else
        sed -i.bak.$t -e "${beg_line_no},${end_line_no}d" $LOCAL_DNS_HOSTS_FILE
    fi

    echo "Done."
    ;;

  *)
    echo "Usage:"
    echo "  $0 enable|disable"
    ;;
esac
