import type { RouteAccess } from "@v1/app/registry/types";
import { makeSession, toV1Session } from "@v1/test";
import { describe, expect, it } from "vitest";
import { type GuardDecision, guardRoute } from "./guard";

const member = toV1Session(makeSession({ role: "user" }));
const admin = toV1Session(makeSession({ role: "admin" }));
const ORG = member.organization.name;

type Who = "guest" | "member" | "admin";
const sessions = { guest: null, member, admin } as const;

// Route type × user → decision, on a URL in the user's organisation.
const MATRIX: Record<RouteAccess, Record<Who, GuardDecision>> = {
  guest: { guest: "allow", member: "enter-app", admin: "enter-app" },
  authenticated: { guest: "sign-in", member: "allow", admin: "allow" },
  admin: { guest: "sign-in", member: "no-permission", admin: "allow" },
  "platform-admin": {
    guest: "sign-in",
    member: "platform-admin",
    admin: "platform-admin",
  },
};

const cases = Object.entries(MATRIX).flatMap(([access, row]) =>
  Object.entries(row).map(
    ([who, decision]) => [access as RouteAccess, who as Who, decision] as const,
  ),
);

describe("guardRoute", () => {
  it.each(cases)("%s route, %s: %s", (access, who, decision) => {
    const session = sessions[who];
    const urlOrganization = access === "guest" ? undefined : ORG;
    expect(guardRoute({ access, session, urlOrganization })).toBe(decision);
  });

  it.each([
    "authenticated",
    "admin",
    "platform-admin",
  ] as const)("%s route in another organisation: go to the current one", (access) => {
    for (const session of [member, admin]) {
      expect(
        guardRoute({ access, session, urlOrganization: "someone-else" }),
      ).toBe("other-organization");
    }
  });

  it("checks the organisation only on routes that name one", () => {
    expect(
      guardRoute({
        access: "authenticated",
        session: member,
        urlOrganization: undefined,
      }),
    ).toBe("allow");
  });

  it("sends a guest to sign in before looking at the organisation", () => {
    expect(
      guardRoute({
        access: "authenticated",
        session: null,
        urlOrganization: "someone-else",
      }),
    ).toBe("sign-in");
  });
});
