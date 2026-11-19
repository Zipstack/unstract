/*
 * What the UI offers the signed-in user. A page removes an action the user
 * may not take; it never shows it disabled. The backend is the authority:
 * these only keep people from filling in a form that can only fail.
 */
import type { Session } from "./session";

/** A shared resource; every shareable resource's serializer sends `is_owner`. */
export type OwnedResource = Readonly<{ is_owner?: boolean }>;

/** The capabilities an organisation admin can open to members. */
export type CapabilityKey =
  | "create_llm_adapters"
  | "create_connectors"
  | "create_other_adapters"
  | "manage_api_keys"
  | "manage_members"
  | "change_platform_defaults"
  | "delete_workflows_and_deployments";

/** One row of `GET organization/capabilities/`; the fields v1 reads. */
export type Capability = Readonly<{
  key: CapabilityKey;
  allowed_for_me: boolean;
}>;

export function isAdmin(session: Session): boolean {
  return session.user.isAdmin;
}

/** Owner or co-owner. */
export function isOwner(resource: OwnedResource): boolean {
  return resource.is_owner === true;
}

/**
 * Owners and organisation admins. While `is_owner` has not loaded, assume
 * yes rather than flash a read-only view at the owner (v0's canEditResource).
 */
export function canEdit(session: Session, resource: OwnedResource): boolean {
  return (
    resource.is_owner === undefined || isOwner(resource) || isAdmin(session)
  );
}

/** Owners and admins may delete a shared resource; see canDeleteWorkflowOrDeployment for those. */
export function canDelete(session: Session, resource: OwnedResource): boolean {
  return canEdit(session, resource);
}

/** Changing who a resource is shared with takes the same as editing it. */
export const canShare = canEdit;

type Capabilities = readonly Capability[] | undefined;

// False until the capabilities have loaded.
const allows = (capabilities: Capabilities, key: CapabilityKey): boolean =>
  capabilities?.some((c) => c.key === key && c.allowed_for_me) ?? false;

/** Whether the organisation's capability settings let the user create `key`, e.g. `create_connectors`. */
export function canCreate(
  capabilities: Capabilities,
  // Use canDeleteWorkflowOrDeployment.
  key: Exclude<CapabilityKey, "delete_workflows_and_deployments">,
): boolean {
  return allows(capabilities, key);
}

/**
 * A workflow, pipeline or API deployment: an owner or admin, and the
 * organisation's delete capability, as the backend's destroy checks.
 */
export function canDeleteWorkflowOrDeployment(
  session: Session,
  resource: OwnedResource,
  capabilities: Capabilities,
): boolean {
  return (
    canDelete(session, resource) &&
    allows(capabilities, "delete_workflows_and_deployments")
  );
}
