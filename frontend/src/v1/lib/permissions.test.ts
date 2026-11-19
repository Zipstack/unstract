import { makeSession, toV1Session } from "@v1/test";
import { describe, expect, it } from "vitest";
import {
  type Capability,
  canCreate,
  canDelete,
  canDeleteWorkflowOrDeployment,
  canEdit,
  canManageSharing,
  isAdmin,
  isOwner,
} from "./permissions";

const admin = toV1Session(makeSession({ role: "admin" }));
const member = toV1Session(makeSession({ role: "user" }));

describe("permissions", () => {
  it("isAdmin and isOwner", () => {
    expect(isAdmin(admin)).toBe(true);
    expect(isAdmin(member)).toBe(false);
    expect(isOwner({ is_owner: true })).toBe(true);
    expect(isOwner({ is_owner: false })).toBe(false);
    expect(isOwner({})).toBe(false);
  });

  it.each([
    canEdit,
    canDelete,
    canManageSharing,
  ])("%o: owners and admins, and anyone while ownership is loading", (can) => {
    expect(can(member, { is_owner: true })).toBe(true);
    expect(can(member, { is_owner: false })).toBe(false);
    expect(can(admin, { is_owner: false })).toBe(true);
    expect(can(member, {})).toBe(true);
  });

  it("canCreate follows the capability settings, and is false until they load", () => {
    const capabilities: Capability[] = [
      { key: "create_connectors", allowed_for_me: true },
      { key: "create_llm_adapters", allowed_for_me: false },
    ];
    expect(canCreate(capabilities, "create_connectors")).toBe(true);
    expect(canCreate(capabilities, "create_llm_adapters")).toBe(false);
    expect(canCreate(capabilities, "manage_members")).toBe(false);
    expect(canCreate(undefined, "create_connectors")).toBe(false);
    // @ts-expect-error use canDeleteWorkflowOrDeployment
    canCreate(capabilities, "delete_workflows_and_deployments");
  });
});

it("canDeleteWorkflowOrDeployment also needs the organisation's delete capability", () => {
  const owned = { is_owner: true };
  const open = [
    { key: "delete_workflows_and_deployments", allowed_for_me: true },
  ] as const;
  const closed = [
    { key: "delete_workflows_and_deployments", allowed_for_me: false },
  ] as const;
  expect(canDeleteWorkflowOrDeployment(member, owned, open)).toBe(true);
  expect(canDeleteWorkflowOrDeployment(member, owned, closed)).toBe(false);
  expect(canDeleteWorkflowOrDeployment(member, owned, undefined)).toBe(false);
  expect(canDeleteWorkflowOrDeployment(member, { is_owner: false }, open)).toBe(
    false,
  );
});
