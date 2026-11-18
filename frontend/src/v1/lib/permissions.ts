/*
 * What the UI offers the signed-in user. A page removes an action the user
 * may not take; it never shows it disabled. The backend is the authority:
 * these only keep people from filling in a form that can only fail.
 */
import type { Session } from "./session";

/** A shared resource; every shareable resource's serializer sends `is_owner`. */
export type OwnedResource = Readonly<{ is_owner?: boolean }>;

/** The capabilities an organisation admin can open to members (UN-4399). */
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

/** Deleting a shared resource takes the same as editing it. */
export const canDelete = canEdit;

/** Changing who a resource is shared with takes the same as editing it. */
export const canShare = canEdit;

/**
 * Whether the organisation's capability settings let the user do `key`, e.g.
 * `create_connectors`. False until the capabilities have loaded.
 */
export function canCreate(
  capabilities: readonly Capability[] | undefined,
  key: CapabilityKey,
): boolean {
  return capabilities?.some((c) => c.key === key && c.allowed_for_me) ?? false;
}
