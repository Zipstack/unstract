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

  // CASA 6.6.1: the user's data must not outlive the session in the browser.
  it("clears browser storage before leaving the page", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "https://app.example/org/dashboard" },
    });
    window.localStorage.setItem("oauth-cachekey-google_drive", "cache-key");
    window.localStorage.setItem("unstract.v1.theme", "dark");
    window.sessionStorage.setItem("oauth-current-connector", "google_drive");

    const { result } = renderHook(() => useLogout());
    result.current();

    expect(
      window.localStorage.getItem("oauth-cachekey-google_drive"),
    ).toBeNull();
    expect(window.localStorage.getItem("unstract.v1.theme")).toBe("dark");
    expect(window.sessionStorage.length).toBe(0);
    window.localStorage.clear();
  });
});
