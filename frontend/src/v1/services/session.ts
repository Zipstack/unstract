import { clearBrowserStorage } from "@v1/lib/browserStorage";
import type { Session } from "@v1/lib/session";
import posthog from "posthog-js";
import { ApiError } from "./errors";
import { createHttpClient, http, orgPath, type RequestOptions } from "./http";
import { LOGOUT_PATH } from "./logout";
import {
  listOrganizations,
  type Organization,
  OrganizationError,
  switchOrganization,
} from "./organizations";
import { reportApiError } from "./report";

type SignalOnly = Pick<RequestOptions, "signal">;

/** The fields of `GET /api/v1/session` v1 reads. */
type SessionReply = Readonly<{
  id: number;
  email: string;
  organization_id: string | null;
  role: string | null;
  is_staff: boolean;
  org_switch_via_login?: boolean;
}>;

/** The fields of `GET users/profile/` v1 reads. */
type ProfileReply = Readonly<{
  name?: string;
  display_name?: string;
  is_admin?: boolean;
  role?: string;
}>;

/**
 * What a page load finds. `choose-organization`: signed in to several
 * organisations and none is current. `ended`: listing them answered 412,
 * which logs the session out; `body` may name the cause. `access-removed`:
 * the session's organisation is no longer the user's. `no-organization`: the
 * user belongs to none.
 */
export type SessionLoad =
  | Readonly<{
      kind: "signed-in";
      session: Session;
      organizations: readonly Organization[];
    }>
  | Readonly<{ kind: "guest" }>
  | Readonly<{
      kind: "choose-organization";
      organizations: readonly Organization[];
    }>
  | Readonly<{ kind: "ended"; body: unknown }>
  | Readonly<{ kind: "access-removed" }>
  | Readonly<{ kind: "no-organization" }>;

const GUEST: SessionLoad = { kind: "guest" };
const ACCESS_REMOVED: SessionLoad = { kind: "access-removed" };

/** Query keys: the session is one per browser, not per organisation. */
export const sessionKeys = { current: () => ["session"] as const };

// Its 401 means signed out, not an expired session, so it sends no one to sign in.
const sessionProbe = createHttpClient({ expiresSession: false });

async function getSessionReply(signal?: AbortSignal) {
  try {
    // A cache-buster, as v0 sends: a cached reply could show a signed-out user as signed in.
    const { data } = await sessionProbe.get<SessionReply>("/api/v1/session", {
      signal,
      params: { q: Date.now() },
    });
    // A proxy or SPA fallback can answer 200 with some other body.
    if (typeof data?.id !== "number") {
      throw new TypeError("Session reply carried no user id");
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError && error.kind === "unauthenticated") {
      return null;
    }
    throw error;
  }
}

async function getProfile(org: string, signal?: AbortSignal) {
  const { data } = await http.get<{ user?: ProfileReply }>(
    orgPath("/users/profile/", org),
    { signal },
  );
  if (!data?.user) {
    throw new TypeError("Profile reply carried no user");
  }
  return data.user;
}

function toSession(
  reply: SessionReply,
  profile: ProfileReply,
  org: Organization,
): Session {
  return {
    user: {
      id: String(reply.id),
      email: reply.email,
      name: profile.display_name || profile.name || reply.email,
      role: profile.role ?? reply.role ?? "",
      isAdmin: profile.is_admin === true,
      isStaff: reply.is_staff === true,
    },
    organization: {
      id: org.id,
      name: org.name,
      displayName: org.display_name,
      switchViaLogin: reply.org_switch_via_login === true,
    },
  };
}

/** The session's organisation if the user is still in it, else their only one. */
function pickOrganization(
  reply: SessionReply,
  organizations: readonly Organization[],
): Organization | undefined {
  const current = organizations.find((o) => o.id === reply.organization_id);
  return current ?? (organizations.length === 1 ? organizations[0] : undefined);
}

// v0 shows its picker only when the session names no organisation.
function withoutOrganization(
  reply: SessionReply,
  organizations: readonly Organization[],
): SessionLoad {
  if (organizations.length === 0) {
    return { kind: "no-organization" };
  }
  return reply.organization_id
    ? ACCESS_REMOVED
    : { kind: "choose-organization", organizations };
}

async function enterOrganization(
  reply: SessionReply,
  org: Organization,
  organizations: readonly Organization[],
  signal?: AbortSignal,
): Promise<SessionLoad> {
  let urlName: string | undefined;
  try {
    urlName = await switchOrganization(org.id, { signal });
  } catch (error) {
    if (!(error instanceof OrganizationError)) {
      throw error;
    }
    // Its 403: access lost after the list loaded, or a refused CSRF token; logged with its request id.
    reportApiError(error.cause, { notify: false });
    return ACCESS_REMOVED;
  }
  const profile = await getProfile(org.id, signal);
  const current = { ...org, name: urlName ?? org.name };
  return {
    kind: "signed-in",
    session: toSession(reply, profile, current),
    organizations,
  };
}

async function listOrEnd(signal?: AbortSignal) {
  try {
    return await listOrganizations({ signal });
  } catch (error) {
    if (error instanceof OrganizationError) {
      return { kind: "ended", body: error.body } as const;
    }
    throw error;
  }
}

/**
 * Loads the session as v0's useSessionValid does: the user, their
 * organisations, then the profile in the current one. Like v0 it sets the
 * organisation on every load, which also syncs the member's role from the
 * identity provider: the session's, if the user is still in it, else their
 * only one.
 */
export async function loadSession({
  signal,
}: SignalOnly = {}): Promise<SessionLoad> {
  const reply = await getSessionReply(signal);
  if (!reply) {
    return GUEST;
  }
  const organizations = await listOrEnd(signal);
  if (!Array.isArray(organizations)) {
    return organizations;
  }
  const org = pickOrganization(reply, organizations);
  return org
    ? enterOrganization(reply, org, organizations, signal)
    : withoutOrganization(reply, organizations);
}

/**
 * Ends the session. Returns the URL to open at top level: the identity
 * provider's sign-out on cloud, the web app on OSS. A script cannot follow a
 * cross-origin sign-out redirect, so the backend answers a POST with the URL.
 */
export async function signOut({ signal }: SignalOnly = {}): Promise<string> {
  const { data } = await http.post<{ redirect_url?: unknown }>(
    LOGOUT_PATH,
    undefined,
    { signal },
  );
  if (typeof data?.redirect_url !== "string" || data.redirect_url === "") {
    throw new Error("Sign-out reply carried no redirect URL");
  }
  const url = new URL(data.redirect_url, window.location.origin);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("Sign-out reply carried a non-http redirect URL");
  }
  return url.href;
}

// A sign-out POST that hangs falls back to the GET rather than keep a dead page on screen.
// Accepted race: a POST that lands just after the abort leaves the GET to skip Unstract ID's sign-out.
export const SIGN_OUT_TIMEOUT_MS = 5000;

async function signOutWithin(ms: number): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await signOut({ signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Signs out, forgets the analytics identity and stored data, and leaves the app. */
export async function signOutAndLeave(): Promise<void> {
  let destination: string;
  try {
    destination = await signOutWithin(SIGN_OUT_TIMEOUT_MS);
  } catch (error) {
    // Logged so a failing POST shows up: the backend drops GET logout once v0
    // goes. Every use of LOGOUT_PATH as a GET (logout.ts, context.ts) must
    // move with it.
    console.error("Sign-out POST failed; falling back to GET", error);
    // The GET logout ends the session too and redirects itself (v0's path).
    destination = LOGOUT_PATH;
  }
  posthog.reset();
  clearBrowserStorage();
  window.location.assign(destination);
}
