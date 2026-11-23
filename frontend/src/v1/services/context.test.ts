import { afterEach, describe, expect, it, vi } from "vitest";
import {
  currentOrganizationId,
  expireSession,
  onSessionExpired,
  setOrganizationId,
} from "./context";

afterEach(() => {
  setOrganizationId(null);
});

describe("currentOrganizationId", () => {
  it("gives the organisation that is set, and throws while none is", () => {
    expect(() => currentOrganizationId()).toThrow(/No organisation is set/);
    setOrganizationId("");
    expect(() => currentOrganizationId()).toThrow(/No organisation is set/);
    setOrganizationId("org-1");
    expect(currentOrganizationId()).toBe("org-1");
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

  it.each([
    [
      "throws",
      () => {
        throw new Error("handler broke");
      },
    ],
    ["rejects", () => Promise.reject(new Error("handler broke"))],
  ])("signs out by default when the handler %s, and logs it", async (_, handler) => {
    const assign = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => undefined);
    const logged = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const cleanup = onSessionExpired(handler);
    expireSession();
    await vi.waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/api/v1/logout"),
    );
    expect(logged).toHaveBeenCalledTimes(1);
    cleanup();
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

describe("whenSessionExpired", () => {
  // The expired state lasts for the page load, so each test takes a fresh module.
  async function freshContext() {
    vi.resetModules();
    return import("./context");
  }

  it("tells listeners when the session expires, and a later one at once", async () => {
    const context = await freshContext();
    vi.spyOn(window.location, "assign").mockImplementation(() => undefined);
    const early = vi.fn();
    const removed = vi.fn();
    context.whenSessionExpired(early);
    context.whenSessionExpired(removed)();
    expect(early).not.toHaveBeenCalled();
    context.expireSession();
    expect(early).toHaveBeenCalledTimes(1);
    expect(removed).not.toHaveBeenCalled();
    const late = vi.fn();
    context.whenSessionExpired(late);
    expect(late).toHaveBeenCalledTimes(1);
  });

  it("still runs the handler when a listener throws", async () => {
    const context = await freshContext();
    const handler = vi.fn();
    const logged = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    context.onSessionExpired(handler);
    context.whenSessionExpired(() => {
      throw new Error("listener broke");
    });
    context.expireSession();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(logged).toHaveBeenCalledTimes(1);
  });
});
