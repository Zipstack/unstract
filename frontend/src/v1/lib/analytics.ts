/*
 * Analytics as v0 captures it (usePostHogEvents.js, PostHogPageviewTracker.js):
 * v0's tracker records page views for v1 URLs too, and v1 events use v0's
 * names. v1 adds the `ui_version` property to every event. Analytics never
 * breaks a page: a failed call is only logged, as in v0.
 */
import posthog from "posthog-js";
import type { Session } from "./session";

export type UiVersion = "v0" | "v1";

// Unstract-managed SaaS (helpers/PostHogDeployment.js); the only hosts that may send PII.
const SAAS_HOSTS: ReadonlySet<string> = new Set([
  "us-central.unstract.com",
  "eu-west.unstract.com",
]);

const OSS_ORGANIZATION = "mock_org";

// PostHog starts only where v0 enables it (index.jsx); otherwise do nothing.
const started = (): boolean => posthog.__loaded === true;

function capture(what: string, call: () => void): void {
  if (!started()) {
    return;
  }
  try {
    call();
  } catch (error) {
    console.error(`[v1 analytics] ${what} failed`, error);
  }
}

/** Tags every later event with the version on screen; call before the page view is captured. */
export function registerUiVersion(version: UiVersion): void {
  capture("register", () => posthog.register({ ui_version: version }));
}

/**
 * Identifies the signed-in user, as v0 does on its authenticated routes. The
 * person's name is left to v0, which builds it from fields v1 does not load.
 */
export function identifyUser({ user, organization }: Session): void {
  const isOpenSource = organization.name === OSS_ORGANIZATION;
  const software = isOpenSource ? "OSS" : "SAAS";
  const canSendPii = SAAS_HOSTS.has(window.location.hostname) && !isOpenSource;
  const distinctId = canSendPii ? user.email : `${organization.id}:${user.id}`;
  const pii = canSendPii ? { email: user.email } : {};
  capture("identify", () => {
    posthog.identify(distinctId, {
      org: organization.name,
      software,
      userId: user.id,
      ...pii,
    });
    posthog.register({
      org_id: organization.id,
      org_name: organization.name,
      software,
    });
  });
}
