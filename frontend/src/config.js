/**
 * Application configuration
 * This file centralizes all configuration values and provides defaults
 * Configuration values are loaded from multiple sources with the following priority:
 * 1. Runtime configuration (from window.RUNTIME_CONFIG) - for containerized environments
 * 2. Environment variables (from import.meta.env) - for development
 * 3. Default values - fallback
 */

// Check if runtime config is available (in containerized environments)
const runtimeConfig =
  typeof window !== "undefined" ? window.RUNTIME_CONFIG || {} : {};

const config = {
  favicon:
    runtimeConfig.faviconPath ||
    process.env.REACT_APP_FAVICON_PATH ||
    "../public/favicon.ico",
  logoUrl: runtimeConfig.logoUrl || process.env.REACT_APP_CUSTOM_LOGO_URL,
  mimetype:
    runtimeConfig.mimetype ||
    process.env.REACT_APP_MIMETYPE ||
    "application/json",
  // Add more values as OR case, if needed for fallback.
};

export default config;