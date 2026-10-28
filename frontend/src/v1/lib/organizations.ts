/** Wording and navigation rules for the organisation switcher (page 19). */

// Stored roles: `admin`/`user` in OSS, `unstract_*` in cloud (account_v2/ReadMe.md).
const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  unstract_admin: "Admin",
  user: "Member",
  unstract_user: "Member",
  unstract_supervisor: "Supervisor",
  unstract_reviewer: "Reviewer",
};

export function roleLabel(role: string | undefined): string | undefined {
  return role === undefined ? undefined : ROLE_LABELS[role];
}

export interface OrganizationDetails {
  role?: string;
  member_count?: number;
  region?: string;
}

/**
 * "Admin · 40 members · US". The list leaves a field out when this deployment
 * cannot answer for it (OSS has no regions), so a missing part is skipped.
 */
export function describeOrganization({
  role,
  member_count,
  region,
}: OrganizationDetails): string {
  const members =
    member_count === undefined
      ? undefined
      : `${member_count} member${member_count === 1 ? "" : "s"}`;
  return [roleLabel(role), members, region].filter(Boolean).join(" · ");
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  return words
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

/** One letter, for the small marks (the account trigger, the organisation pill). */
export function initial(name: string): string {
  return name.trim()[0]?.toUpperCase() ?? "?";
}

/** Two letters for an organisation avatar; a one-word name gives its first two. */
export function organizationInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  const letters =
    words.length === 1 ? [...words[0]].slice(0, 2) : words.map((w) => w[0]);
  return letters.slice(0, 2).join("").toUpperCase();
}

/**
 * Where the app lands after switching: the same section in the new
 * organisation, else its dashboard. Paths are `/<org name>/<section>/...`.
 * ponytail: keeps only the section, since a record id below it belongs to the
 * old organisation; ask the route registry which sections exist once it does.
 */
export function landingPath(
  pathname: string,
  fromOrg: string,
  toOrg: string,
): string {
  const [org, section] = pathname.split("/").filter(Boolean);
  return org === fromOrg && section
    ? `/${toOrg}/${section}`
    : `/${toOrg}/dashboard`;
}
