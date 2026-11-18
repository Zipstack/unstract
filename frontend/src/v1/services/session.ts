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
 * which logs the session out; `body` may name the cause.
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
  | Readonly<{ kind: "ended"; body: unknown }>;

const GUEST: SessionLoad = { kind: "guest" };

/** Query keys: the session is one per browser, not per organisation. */
export const sessionKeys = { current: () => ["session"] as const };

// Its 401 means signed out, not an expired session, so it sends no one to sign in.
const sessionProbe = createHttpClient({ expiresSession: false });

async function getSessionReply(signal?: AbortSignal) {
  try {
    const { data } = await sessionProbe.get<SessionReply>("/api/v1/session", {
      signal,
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
  // v0 treats a user with no organisation as signed out.
  if (organizations.length === 0) {
    console.warn("[v1 session] the user belongs to no organisation");
    return GUEST;
  }
  const org = pickOrganization(reply, organizations);
  if (!org) {
    return { kind: "choose-organization", organizations };
  }
  await switchOrganization(org.id, { signal });
  const profile = await getProfile(org.id, signal);
  return {
    kind: "signed-in",
    session: toSession(reply, profile, org),
    organizations,
  };
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
