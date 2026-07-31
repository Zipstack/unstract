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

// Name of the default org for the open-source deployment. Must match the backend
// DEFAULT_ORGANIZATION_NAME so the open-source check stays correct. Trimmed with a
// blank fallback to mirror the backend (which strips DEFAULT_ORGANIZATION_NAME), so
// surrounding whitespace can't desync open-source detection.
const rawDefaultOrgName =
  runtimeConfig.defaultOrgName ||
  import.meta.env.VITE_DEFAULT_ORG_NAME ||
  "mock_org";
const defaultOrgName = rawDefaultOrgName.trim() || "mock_org";

const config = {
  favicon:
    runtimeConfig.faviconPath ||
    import.meta.env.VITE_FAVICON_PATH ||
    "/favicon.ico",
  logoUrl: runtimeConfig.logoUrl || import.meta.env.VITE_CUSTOM_LOGO_URL,
  version: runtimeConfig.version || import.meta.env.VITE_VERSION,
  defaultOrgName,
  // Add more values as OR case, if needed for fallback.
};

export default config;
