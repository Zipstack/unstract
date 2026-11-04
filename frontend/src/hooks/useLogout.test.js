import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../store/session-store";

vi.mock("posthog-js/react", () => ({
  usePostHog: () => ({ reset: vi.fn() }),
}));

const { default: useLogout } = await import("./useLogout.js");

describe("useLogout", () => {
  const original = window.location;

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: original,
    });
  });

  // The backend's redirects end at the identity provider, which answers no
  // CORS request: only a page navigation can follow them to /landing.
  it("leaves the page for the backend logout", () => {
    const location = { href: "https://app.example/org/dashboard" };
    Object.defineProperty(window, "location", {
      configurable: true,
      value: location,
    });

    const { result } = renderHook(() => useLogout());
    result.current();

    expect(location.href).toMatch(/\/api\/v1\/logout$/);
    expect(useSessionStore.getState().isLogoutLoading).toBe(true);
  });
});
