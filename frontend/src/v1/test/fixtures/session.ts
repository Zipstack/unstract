/* Fixtures for the session load (services/session.ts), typed against its contract. */

import type { Organization } from "@v1/services/organizations";
import { HttpResponse, http, type TestSession } from "@v1/test";

/** The row `GET /api/v1/organization` lists for a fixture's organisation. */
export function organizationRow({ organization, role }: TestSession) {
  return {
    id: organization.id,
    name: organization.urlName,
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

type Seen = (request: Request) => void;

function sessionReply(
  { user, role }: TestSession,
  current: string | null,
  isStaff: boolean,
) {
  return {
    id: Number(user.id),
    email: user.email,
    organization_id: current,
    role,
    is_staff: isStaff,
  };
}

function profileReply({ user, role }: TestSession) {
  const name = user.displayName;
  return {
    user: { name, display_name: name, role, is_admin: role === "admin" },
  };
}

/** Answers the session load as `session`: the session, the organisation list, set, and the profile. */
export function sessionHandlers(
  session: TestSession,
  options: SessionHandlerOptions = {},
) {
  const current =
    options.current === undefined ? session.organization.id : options.current;
  const organizations = options.organizations ?? [organizationRow(session)];
  const seen: Seen = (request) =>
    options.seen?.push(`${request.method} ${new URL(request.url).pathname}`);
  const answer = (
    path: string,
    method: "get" | "post",
    body: () => Record<string, unknown>,
  ) =>
    http[method](path, ({ request }) => {
      seen(request);
      return HttpResponse.json(body());
    });
  return [
    answer("/api/v1/session", "get", () =>
      sessionReply(session, current, options.isStaff ?? false),
    ),
    answer("/api/v1/organization", "get", () => ({ organizations })),
    answer("/api/v1/organization/:id/set", "post", () => ({})),
    answer("/api/v1/unstract/:org/users/profile/", "get", () =>
      profileReply(session),
    ),
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
