// Service-account address minted by `create_api_user_for_key`. Its owner is a
// platform API key, not a person, so the field is labelled rather than named.
const PLATFORM_KEY_EMAIL_DOMAIN = "@platform.internal";

/**
 * Resolve the "Owned By" label for a resource row.
 *
 * Shared by the list table and the card views so the two cannot drift — they
 * previously disagreed on both the source field and the "Me" rule.
 *
 * @param {object} item Resource row from a list endpoint.
 * @param {object} sessionDetails Current session, for the "Me" comparison.
 * @param {string} ownerEmailsProp Field holding the owner emails.
 * @return {{email: string|undefined, name: string, extra: string}}
 */
function resolveOwnerDisplay(item, sessionDetails, ownerEmailsProp) {
  // owner_emails is earliest-first; [0] is the primary shown owner. Fall back
  // to created_by_email so rows with no live OWNER membership (pre-backfill
  // rows) don't render "Unknown".
  const ownerEmails = item?.[ownerEmailsProp ?? "owner_emails"];
  const rawEmail =
    (Array.isArray(ownerEmails) ? ownerEmails[0] : undefined) ??
    item?.created_by_email;
  // Reached only when a platform key's creator has since been deleted, so no
  // human can be named. Suppress the synthetic address rather than dress a
  // machine identity up as a colleague.
  const isPlatformKey = Boolean(rawEmail?.endsWith(PLATFORM_KEY_EMAIL_DOMAIN));
  const email = isPlatformKey ? undefined : rawEmail;
  // "Me" must track the DISPLAYED owner, not the viewer's own membership —
  // else a co-owner sees "Me" over the primary owner's avatar/email. Match on
  // the shown email so the creator viewing their own resource still reads "Me".
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
