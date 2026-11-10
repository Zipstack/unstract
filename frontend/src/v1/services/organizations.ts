import { http } from "@v1/lib/http";
import type { OrganizationDetails } from "@v1/lib/organizations";

/** A row of GET /api/v1/organization. role, member_count and region may be absent. */
export interface Organization extends OrganizationDetails {
  id: string;
  /** The URL name: paths are /<name>/... */
  name: string;
  display_name: string;
}

export async function listOrganizations(): Promise<Organization[]> {
  const { data } = await http.get<{ organizations: Organization[] }>(
    "/api/v1/organization",
  );
  return data.organizations;
}

/** Makes the organisation the session's current one. */
export async function switchOrganization(id: string): Promise<void> {
  await http.post(`/api/v1/organization/${encodeURIComponent(id)}/set`);
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
