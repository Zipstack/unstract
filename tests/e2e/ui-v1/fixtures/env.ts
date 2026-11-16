/**
 * Environment the suite reads. The rig exports the URLs when it boots the
 * platform (`python -m tests.rig run frontend-v1-e2e`); the fallbacks match the
 * ports compose publishes.
 */

export const FRONTEND_URL =
  process.env.UNSTRACT_FRONTEND_URL ?? "http://localhost:3000";

export const BACKEND_URL = (
  process.env.UNSTRACT_BACKEND_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

/**
 * Set by tests/rig/cli.py for every `requires_platform` group. When present
 * the rig already proved the stack answers, so an unreachable app or a failed
 * login is a real failure, not a reason to skip.
 */
export const RIG_MANAGED = Boolean(process.env.UNSTRACT_RIG_SESSION_ID);

export type AuthMode = "oss" | "auth0";

export function configuredAuthMode(): AuthMode | "auto" {
  const explicit = process.env.UNSTRACT_AUTH_MODE?.toLowerCase();
  return explicit === "oss" || explicit === "auth0" ? explicit : "auto";
}

/** Pins the organisation to select; the first one the user has otherwise. */
export const ORG_ID = process.env.UNSTRACT_E2E_ORG_ID || undefined;
