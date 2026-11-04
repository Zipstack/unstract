/** The build a test renders under; cloud and on-prem builds carry v1 plugins. */
export type Distribution = "oss" | "cloud" | "onprem";

/** A colour mode the v1 root can carry; mirrors ThemeMode from #2399. */
export type ThemeMode = "light" | "dark" | "unstract";

export type TestUser = Readonly<{
  id: string;
  email: string;
  displayName: string;
}>;

export type TestOrganization = Readonly<{
  id: string;
  name: string;
}>;

/** The signed-in user a test renders as. `null` in render options means signed out. */
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

export const DEFAULT_DISTRIBUTION: Distribution = "oss";

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
