#!/bin/bash

# Start the first process
# Args: --nocrashreport --nodefault
/usr/bin/libreoffice --headless --nologo --nofirststartwizard --norestore --accept="socket,host=127.0.0.1,port=2002,tcpNoDelay=1;urp;StarOffice.ComponentContext" &

# Start the second process
# 'src' layout is detected from pdm settings in pyproject.toml
.venv/bin/gunicorn --bind 0.0.0.0:3002 --timeout 300 unstract.document_service.main:app &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
