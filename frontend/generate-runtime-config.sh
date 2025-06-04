#!/bin/sh

# This script generates a runtime config file with environment variables
# It will be executed when the container starts

# Create config directory if it doesn't exist
mkdir -p /usr/share/nginx/html/config

# Generate the runtime-config.js file with the current environment variables
cat > /usr/share/nginx/html/config/runtime-config.js << EOF
// This file is auto-generated at runtime. Do not modify manually.
window.RUNTIME_CONFIG = {
  faviconPath: "${REACT_APP_FAVICON_PATH}",
  logoUrl: "${REACT_APP_CUSTOM_LOGO_URL}",
  mimetype: "${REACT_APP_MIMETYPE:-application/json}"
};
EOF

# Make sure nginx can read the file
chmod 755 /usr/share/nginx/html/config/runtime-config.js

echo "Runtime configuration generated successfully with logo URL: ${REACT_APP_CUSTOM_LOGO_URL:-<not set>}"
