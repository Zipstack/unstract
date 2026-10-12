// Service accounts live in this domain; label them rather than name them.
const PLATFORM_KEY_EMAIL_DOMAIN = "@platform.internal";

/**
 * Resolve the "Owned By" label for a resource row. Shared by the table and
 * card views so the two cannot drift.
 *
 * @param {object} item Resource row from a list endpoint.
 * @param {object} sessionDetails Current session, for the "Me" comparison.
 * @param {string} ownerEmailsProp Field holding the owner emails.
 * @return {{email: string|undefined, name: string, extra: string}}
 */
function resolveOwnerDisplay(item, sessionDetails, ownerEmailsProp) {
  // Earliest owner first; created_by_email covers rows with no OWNER row.
  const ownerEmails = item?.[ownerEmailsProp ?? "owner_emails"];
  const rawEmail =
    (Array.isArray(ownerEmails) ? ownerEmails[0] : undefined) ??
    item?.created_by_email;
  const isPlatformKey = Boolean(rawEmail?.endsWith(PLATFORM_KEY_EMAIL_DOMAIN));
  const email = isPlatformKey ? undefined : rawEmail;
  // Tracks the displayed owner, not the viewer's own membership.
  const isMe = Boolean(email) && email === sessionDetails?.email;
  let name = email?.split("@")[0] || "Unknown";
  if (isPlatformKey) {
    name = "Platform key";
  } else if (isMe) {
    name = "Me";
  }
  const extra =
    item?.co_owners_count > 1 ? ` +${item.co_owners_count - 1}` : "";
  return { email, name, extra };
}

export { resolveOwnerDisplay };
