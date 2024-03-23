#! /bin/sh

script_dir=$(dirname "$(readlink -f "$BASH_SOURCE")")

cd $script_dir/../../backend

# Check Django default db connectivity.
# Use Python for cross-platform compatibility.
python << EOF
import os
import socket
import sys

import dotenv

dotenv.load_dotenv()

def _check_connectivity(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        errno = s.connect_ex((host, port))
        return errno

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", 5432))

errno = _check_connectivity(db_host, db_port)

if errno == 0:
    print("Django default db ok:", os.strerror(errno))
    sys.exit(0)
else:
    print("Django default db error:", os.strerror(errno))
    sys.exit(1)
EOF
if [ $? -ne 0 ]; then
    echo ""
    echo "Check DB_HOST, DB_PORT settings for Django default db."
    echo "If db is running in a container, add DB_HOST to /etc/hosts."
    echo ""
    exit 1
fi

# Check Django migrations.
python manage.py makemigrations --check --dry-run --no-input
# ! IMPORTANT !
# Above command does not return error exit code
# on network error when connecting to db.
exit 0
