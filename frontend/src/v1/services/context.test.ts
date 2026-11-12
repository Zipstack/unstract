import { afterEach, describe, expect, it, vi } from "vitest";
import {
  currentOrganizationId,
  expireSession,
  onSessionExpired,
  orgPath,
  setOrganizationId,
} from "./context";

afterEach(() => {
  setOrganizationId(null);
});

describe("orgPath", () => {
  it("builds the org-scoped path and keeps the trailing slash as written", () => {
    setOrganizationId("org-1");
    expect(orgPath("/adapter/")).toBe("/api/v1/unstract/org-1/adapter/");
    expect(orgPath("/adapter/info/a1/")).toBe(
      "/api/v1/unstract/org-1/adapter/info/a1/",
    );
    expect(orgPath("/flags")).toBe("/api/v1/unstract/org-1/flags");
  });

  it("encodes the organisation id, so it stays one segment", () => {
    setOrganizationId("a/b c");
    expect(orgPath("/x/")).toBe("/api/v1/unstract/a%2Fb%20c/x/");
  });

  it("throws while no organisation is set", () => {
    expect(() => orgPath("/adapter/")).toThrow(/No organisation is set/);
    setOrganizationId("");
    expect(() => currentOrganizationId()).toThrow(/No organisation is set/);
  });
});

describe("session expiry", () => {
  it("sends the browser to the logout URL by default", () => {
    const assign = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => undefined);
    expireSession();
    expect(assign).toHaveBeenCalledWith("/api/v1/logout");
  });

  it("runs a registered handler instead, until its cleanup", () => {
    const assign = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => undefined);
    const handler = vi.fn();
    const cleanup = onSessionExpired(handler);
    expireSession();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(assign).not.toHaveBeenCalled();
    cleanup();
    expireSession();
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it("keeps a newer handler when an older one's cleanup runs", () => {
    const older = onSessionExpired(vi.fn());
    const newer = vi.fn();
    const cleanup = onSessionExpired(newer);
    older();
    expireSession();
    expect(newer).toHaveBeenCalledTimes(1);
    cleanup();
  });
});
