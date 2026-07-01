#!/bin/sh

# This script generates a runtime config file with environment variables
# It will be executed when the container starts

# Generate the runtime-config.js file with the current environment variables
# Note: Using VITE_ prefix for Vite compatibility, fallback to REACT_APP_ for backward compatibility

# Escape backslashes and double quotes so values stay valid inside JS strings
js_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

APP_VERSION=$(js_escape "${UNSTRACT_APPS_VERSION:-}")

cat > /usr/share/nginx/html/config/runtime-config.js << EOF
// This file is auto-generated at runtime. Do not modify manually.
window.RUNTIME_CONFIG = {
  faviconPath: "${VITE_FAVICON_PATH:-${REACT_APP_FAVICON_PATH}}",
  logoUrl: "${VITE_CUSTOM_LOGO_URL:-${REACT_APP_CUSTOM_LOGO_URL}}",
  enablePosthog: "${VITE_ENABLE_POSTHOG:-${REACT_APP_ENABLE_POSTHOG}}",
  version: "${APP_VERSION}"
};
EOF

# Make sure nginx can read the file
chmod 755 /usr/share/nginx/html/config/runtime-config.js

echo "Runtime configuration generated successfully with logo URL: ${VITE_CUSTOM_LOGO_URL:-${REACT_APP_CUSTOM_LOGO_URL:-<not set>}}, enablePosthog: ${VITE_ENABLE_POSTHOG:-${REACT_APP_ENABLE_POSTHOG:-<not set>}}"
