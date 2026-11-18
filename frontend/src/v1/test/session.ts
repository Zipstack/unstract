import type { Session } from "@v1/lib/session";
import type { ThemeMode } from "@v1/lib/theme";

/** A colour mode the v1 root can carry (#2399's ThemeMode). */
export type { ThemeMode };

export type TestUser = Readonly<{
  id: string;
  email: string;
  displayName: string;
}>;

export type TestOrganization = Readonly<{
  id: string;
  name: string;
}>;

/**
 * A signed-in user and organization: what `renderV1`'s `session` option
 * provides, and fixture data for network mocks (`apiPath(session, …)` builds
 * the org-scoped URL; `sessionHandlers` answers the session load). The
 * organisation's URL name is its id, as in OSS; `name` is its display name.
 */
export type TestSession = Readonly<{
  user: TestUser;
  organization: TestOrganization;
  role: "admin" | "user";
}>;

export type TestSessionOverrides = Readonly<{
  user?: Partial<TestUser>;
  organization?: Partial<TestOrganization>;
  role?: TestSession["role"];
}>;

export const DEFAULT_SESSION: TestSession = {
  // Numeric, as the session endpoint gives it.
  user: { id: "1", email: "ada@example.com", displayName: "Ada" },
  organization: { id: "org-1", name: "Example Org" },
  role: "admin",
};

export const DEFAULT_THEME: ThemeMode = "light";

/** DEFAULT_SESSION with `overrides` merged one level deep. */
export function makeSession(overrides: TestSessionOverrides = {}): TestSession {
  return {
    user: { ...DEFAULT_SESSION.user, ...overrides.user },
    organization: {
      ...DEFAULT_SESSION.organization,
      ...overrides.organization,
    },
    role: overrides.role ?? DEFAULT_SESSION.role,
  };
}

/** The v1 session a fixture loads as: what `useSession()` gives under `renderV1`. */
export function toV1Session({
  user,
  organization,
  role,
}: TestSession): Session {
  return {
    user: {
      id: user.id,
      email: user.email,
      name: user.displayName,
      role,
      isAdmin: role === "admin",
      isStaff: false,
    },
    organization: {
      id: organization.id,
      name: organization.id,
      displayName: organization.name,
      switchViaLogin: false,
    },
  };
}
