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
 * A signed-in user and organization, as fixture data for network mocks
 * (`apiPath(session, …)` builds the org-scoped URL). Not a render option: no
 * v1 provider reads a session yet.
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
  user: { id: "user-1", email: "ada@example.com", displayName: "Ada" },
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
