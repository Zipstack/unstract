import { http } from "@v1/lib/http";
import type { OrganizationDetails } from "@v1/lib/organizations";
import axios from "axios";

/** A row of GET /api/v1/organization. role, member_count and region may be absent. */
export interface Organization extends OrganizationDetails {
  id: string;
  /** The URL name: paths are /<name>/... */
  name: string;
  display_name: string;
}

/**
 * A refusal the backend gives a meaning to. `session-ended`: the list call
 * answered 412 after logging the session out; `body` may name the cause.
 * `access-removed`: the set call answered 403, so the user left that
 * organisation after the list loaded. Any other failure is thrown as is.
 */
export class OrganizationError extends Error {
  readonly kind: "session-ended" | "access-removed";
  readonly body: unknown;

  constructor(kind: OrganizationError["kind"], body?: unknown) {
    super(`Organisation request refused: ${kind}`);
    this.name = "OrganizationError";
    this.kind = kind;
    this.body = body;
  }
}

function refusal(
  error: unknown,
  status: number,
  kind: OrganizationError["kind"],
): unknown {
  return axios.isAxiosError(error) && error.response?.status === status
    ? new OrganizationError(kind, error.response.data)
    : error;
}

export async function listOrganizations(): Promise<Organization[]> {
  let data: { organizations?: unknown } | undefined;
  try {
    ({ data } = await http.get<{ organizations?: unknown }>(
      "/api/v1/organization",
    ));
  } catch (error) {
    throw refusal(error, 412, "session-ended");
  }
  // A proxy or SPA fallback can answer 200 with some other body.
  if (!Array.isArray(data?.organizations)) {
    throw new Error("Organization list reply carried no organizations");
  }
  return data.organizations as Organization[];
}

/** Makes the organisation the session's current one. */
export async function switchOrganization(id: string): Promise<void> {
  try {
    await http.post(`/api/v1/organization/${encodeURIComponent(id)}/set`);
  } catch (error) {
    throw refusal(error, 403, "access-removed");
  }
}

/**
 * Where to send the browser to switch when the identity provider picked the
 * organisation at login (the session's `org_switch_via_login`): a new login
 * naming it, so the provider records the choice for every product. `prompt=none`
 * shows no screen, since the provider already has a session.
 */
export function organizationLoginUrl(id: string): string {
  const query = new URLSearchParams({ organization: id, prompt: "none" });
  return `/api/v1/login?${query.toString()}`;
}
