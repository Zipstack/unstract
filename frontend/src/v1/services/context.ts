// What the HTTP client takes from the session (UN-4314): the org and expiry handling.

// v0's target too. GET goes when v0 retires (account_v2/views.py), so UN-4314's handler uses the POST sign-out.
const SESSION_EXPIRED_URL = "/api/v1/logout";

export type SessionExpiredHandler = () => void;

const leaveForLogin: SessionExpiredHandler = () => {
  window.location.assign(SESSION_EXPIRED_URL);
};

let sessionExpiredHandler: SessionExpiredHandler = leaveForLogin;
let organizationId: string | null = null;

/** Sets the organisation org-scoped paths use. */
export function setOrganizationId(id: string | null): void {
  organizationId = id;
}

/** The current organisation id; throws while none is set. */
export function currentOrganizationId(): string {
  if (!organizationId) {
    throw new Error(
      "No organisation is set; the session sets it with setOrganizationId().",
    );
  }
  return organizationId;
}

/**
 * Replaces what happens on session expiry (default: v0's logout redirect).
 * The handler must leave the page: the client calls it once per page load.
 * Returns a cleanup that restores the default if this handler is current.
 */
export function onSessionExpired(handler: SessionExpiredHandler): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) {
      sessionExpiredHandler = leaveForLogin;
    }
  };
}

/** Runs the current session-expiry handler; the client calls it once. */
export function expireSession(): void {
  sessionExpiredHandler();
}
