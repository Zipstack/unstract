import { describe, expect, it } from "vitest";

import { resolveOwnerDisplay } from "./owner-display";

const SESSION = { email: "me@example.com" };

describe("resolveOwnerDisplay", () => {
  it("prefers the first owner email over created_by_email", () => {
    const { email, name } = resolveOwnerDisplay(
      {
        owner_emails: ["owner@example.com"],
        created_by_email: "creator@example.com",
      },
      SESSION,
    );
    expect(email).toBe("owner@example.com");
    expect(name).toBe("owner");
  });

  it("falls back to created_by_email when owner_emails is absent or empty", () => {
    for (const item of [
      { created_by_email: "creator@example.com" },
      { owner_emails: [], created_by_email: "creator@example.com" },
    ]) {
      expect(resolveOwnerDisplay(item, SESSION).email).toBe(
        "creator@example.com",
      );
    }
  });

  it("labels a service-account address 'Platform key' and shows no email", () => {
    const { email, name } = resolveOwnerDisplay(
      { created_by_email: "svc-key-1a2b3c4d@platform.internal" },
      SESSION,
    );
    expect(name).toBe("Platform key");
    expect(email).toBeUndefined();
  });

  it("reads 'Me' only when the DISPLAYED owner is the viewer", () => {
    expect(
      resolveOwnerDisplay({ owner_emails: ["me@example.com"] }, SESSION).name,
    ).toBe("Me");
    // A co-owner viewing a resource someone else owns must not read "Me".
    expect(
      resolveOwnerDisplay({ owner_emails: ["other@example.com"] }, SESSION)
        .name,
    ).toBe("other");
  });

  it("suffixes the extra co-owners, and nothing when there is one owner", () => {
    const item = { owner_emails: ["a@example.com"] };
    expect(
      resolveOwnerDisplay({ ...item, co_owners_count: 3 }, SESSION).extra,
    ).toBe(" +2");
    expect(
      resolveOwnerDisplay({ ...item, co_owners_count: 1 }, SESSION).extra,
    ).toBe("");
  });

  it("renders 'Unknown' when the row carries no owner field at all", () => {
    expect(resolveOwnerDisplay({}, SESSION).name).toBe("Unknown");
  });
});
