import { afterEach, describe, expect, it, vi } from "vitest";
import { clearBrowserStorage } from "./browserStorage";

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
});
