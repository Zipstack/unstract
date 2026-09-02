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
  return Boolean(resource?.is_owner || sessionDetails?.isAdmin);
}

export { canEditResource };
