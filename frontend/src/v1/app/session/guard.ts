import type { RouteAccess } from "@v1/app/registry/types";
import type { Session } from "@v1/lib/session";

/*
 * The route guards: v1's counterpart of v0's RequireAuth, RequireGuest and
 * RequireAdmin, with the rules in src/v1/README.md (Session and guards).
 * Pure, so the matrix is unit tested.
 */

export type GuardInput = Readonly<{
  access: RouteAccess;
  /** Null for a guest. */
  session: Session | null;
  /** The URL's `:orgName`; undefined on a route outside an organisation. */
  urlOrganization: string | undefined;
}>;

/**
 * `allow`: render the page. `sign-in`: to login, remembering the URL.
 * `enter-app`: a signed-in user on a guest-only page goes into the app.
 * `choose-organization`: the URL names an organisation that is not current.
 * `no-permission`: the no-permission state. `platform-admin`: the cloud
 * gate decides; without one, no permission.
 */
export type GuardDecision =
  | "allow"
  | "sign-in"
  | "enter-app"
  | "choose-organization"
  | "no-permission"
  | "platform-admin";

export function guardRoute({
  access,
  session,
  urlOrganization,
}: GuardInput): GuardDecision {
  if (access === "guest") {
    return session ? "enter-app" : "allow";
  }
  if (!session) {
    return "sign-in";
  }
  if (
    urlOrganization !== undefined &&
    urlOrganization !== session.organization.name
  ) {
    return "choose-organization";
  }
  if (access === "admin") {
    return session.user.isAdmin ? "allow" : "no-permission";
  }
  return access === "platform-admin" ? "platform-admin" : "allow";
}
