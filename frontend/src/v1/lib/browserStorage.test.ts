import { afterEach, describe, expect, it, vi } from "vitest";
import { clearBrowserStorage, clearUserLocalStorage } from "./browserStorage";

describe("clearBrowserStorage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("removes the user's data and keeps only UI preferences", () => {
    const kept = {
      selectedProduct: "unstract",
      collapsed: "true",
      sidebarPinned: "false",
      "unstract.v1.theme": "dark",
      "unstract.v1.preview": "[]",
      aps_onboarding_stepper_dismissed: "true",
      unstract_welcome_card_dismissed: "true",
      "unstract.v1.oldVersion.7": "true",
    };
    const removed = {
      "dashboard_metrics_overview?org=1": '{"data":{}}',
      "oauth-cachekey-google_drive": "cache-key",
      "unstract.v1.lastUser": "7",
    };
    for (const [key, value] of Object.entries({ ...kept, ...removed })) {
      window.localStorage.setItem(key, value);
    }
    window.sessionStorage.setItem("oauth-current-connector", "google_drive");

    clearBrowserStorage();

    const remaining = Object.fromEntries(
      Object.keys(window.localStorage).map((key) => [
        key,
        window.localStorage.getItem(key),
      ]),
    );
    expect(remaining).toEqual(kept);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("does not throw when storage is unavailable", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(() => clearBrowserStorage()).not.toThrow();
  });

  // Used when the server reports no session: sessionStorage is per tab and
  // holds loop guards (silent sign-in), so only localStorage is cleared.
  it("clearUserLocalStorage leaves sessionStorage alone", () => {
    window.localStorage.setItem("oauth-cachekey-google_drive", "cache-key");
    window.localStorage.setItem("unstract.v1.theme", "dark");
    window.sessionStorage.setItem("unstract:silentSignInAt", "1");

    clearUserLocalStorage();

    expect(
      window.localStorage.getItem("oauth-cachekey-google_drive"),
    ).toBeNull();
    expect(window.localStorage.getItem("unstract.v1.theme")).toBe("dark");
    expect(window.sessionStorage.getItem("unstract:silentSignInAt")).toBe("1");
  });
});
