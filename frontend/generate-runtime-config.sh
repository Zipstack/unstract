#!/bin/sh

# This script generates a runtime config file with environment variables
# It will be executed when the container starts

# Generate the runtime-config.js file with the current environment variables
# Note: Using VITE_ prefix for Vite compatibility, fallback to REACT_APP_ for backward compatibility
cat > /usr/share/nginx/html/config/runtime-config.js << EOF
// This file is auto-generated at runtime. Do not modify manually.
window.RUNTIME_CONFIG = {
  faviconPath: "${VITE_FAVICON_PATH:-${REACT_APP_FAVICON_PATH}}",
  logoUrl: "${VITE_CUSTOM_LOGO_URL:-${REACT_APP_CUSTOM_LOGO_URL}}"
};
EOF

# Make sure nginx can read the file
chmod 755 /usr/share/nginx/html/config/runtime-config.js

echo "Runtime configuration generated successfully with logo URL: ${VITE_CUSTOM_LOGO_URL:-${REACT_APP_CUSTOM_LOGO_URL:-<not set>}}"
