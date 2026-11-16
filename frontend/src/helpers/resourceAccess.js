/**
 * Whether the current user owns a shared resource.
 *
 * True for owners, co-owners and org admins. What that unlocks is per
 * resource and the backend is the authority: on most resources sharing grants
 * read only, while Prompt Studio and Agentic Prompt Studio are shared for
 * collaboration and hold back only the name, delete and access changes.
 * This only decides what the UI offers, so nobody fills in a form that can
 * only fail — it is not itself the rule.
 *
 * `is_owner` is set by every shareable resource's serializer.
 */
function canEditResource(resource, sessionDetails) {
  // Payload not in yet. The backend still refuses the write, so assume
  // editable rather than flash a read-only view at the resource's own owner
  // while the request is in flight.
  if (resource?.is_owner === undefined) {
    return true;
  }
  return Boolean(resource.is_owner || sessionDetails?.isAdmin);
}

export { canEditResource };
