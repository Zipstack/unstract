/**
 * Whether the current user may change a shared resource.
 *
 * Sharing — direct, via group, or org-wide — grants READ only. Owners,
 * co-owners and org admins may edit and delete. The backend is the authority
 * (`is_workflow_mutator` and the `IsOwner` family); this only decides what the
 * UI offers, so nobody fills in a form that can only fail.
 *
 * `is_owner` is set by every shareable resource's serializer.
 */
function canEditResource(resource, sessionDetails) {
  // Payload not in yet. The backend still refuses the write, so assume
  // editable rather than flash a read-only view at the resource's own owner
  // while the request is in flight.
  if (!resource || resource.is_owner === undefined) {
    return true;
  }
  return Boolean(resource.is_owner || sessionDetails?.isAdmin);
}

export { canEditResource };
