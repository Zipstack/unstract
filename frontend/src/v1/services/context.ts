// What the HTTP client takes from the session (UN-4314): the org and expiry handling.

// v0's target too: the backend ends the session and lands on the login page.
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

/** `/api/v1/unstract/<org>` + path, the trailing slash kept as written. */
export function orgPath(path: `/${string}`): string {
  const org = encodeURIComponent(currentOrganizationId());
  return `/api/v1/unstract/${org}${path}`;
}

/**
 * Replaces what happens on session expiry (default: v0's logout redirect).
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
