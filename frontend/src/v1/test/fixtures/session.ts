/* Fixtures for the session load (services/session.ts), typed against its contract. */

import type { Organization } from "@v1/services/organizations";
import { HttpResponse, http, type TestSession } from "@v1/test";

/** The row `GET /api/v1/organization` lists for a fixture's organisation. */
export function organizationRow({ organization, role }: TestSession) {
  return {
    id: organization.id,
    name: organization.id,
    display_name: organization.name,
    role,
  } satisfies Organization;
}

export type SessionHandlerOptions = Readonly<{
  /** The session's organisation id; null while none is set. Default the fixture's. */
  current?: string | null;
  /** What the organisation list answers. Default the fixture's organisation. */
  organizations?: readonly Organization[];
  isStaff?: boolean;
  /** Records each request, as `METHOD path`. */
  seen?: string[];
}>;

/** Answers the session load as `session`: the session, the organisation list, set, and the profile. */
export function sessionHandlers(
  session: TestSession,
  options: SessionHandlerOptions = {},
) {
  const { user, organization, role } = session;
  const current =
    options.current === undefined ? organization.id : options.current;
  const organizations = options.organizations ?? [organizationRow(session)];
  const seen = (request: Request) =>
    options.seen?.push(`${request.method} ${new URL(request.url).pathname}`);
  return [
    http.get("/api/v1/session", ({ request }) => {
      seen(request);
      return HttpResponse.json({
        id: Number(user.id),
        email: user.email,
        organization_id: current,
        role,
        is_staff: options.isStaff ?? false,
      });
    }),
    http.get("/api/v1/organization", ({ request }) => {
      seen(request);
      return HttpResponse.json({ organizations });
    }),
    http.post("/api/v1/organization/:id/set", ({ request }) => {
      seen(request);
      return HttpResponse.json({});
    }),
    http.get("/api/v1/unstract/:org/users/profile/", ({ request }) => {
      seen(request);
      const name = user.displayName;
      const profile = { name, display_name: name, role };
      return HttpResponse.json({
        user: { ...profile, is_admin: role === "admin" },
      });
    }),
  ];
}

/** Answers the session with the auth middleware's 401: nobody is signed in. */
export function guestHandlers() {
  return [
    http.get("/api/v1/session", () =>
      HttpResponse.json({ message: "Unauthorized" }, { status: 401 }),
    ),
  ];
}
