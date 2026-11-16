import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearBrowserStorage,
  clearUserLocalStorage,
  reloadWhenSignedOutElsewhere,
} from "./browserStorage";

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

// Another tab is another BroadcastChannel on the same name.
function otherTab(): BroadcastChannel {
  return new BroadcastChannel("unstract.session");
}

/** Resolves once pending channel messages have been delivered. */
function delivered(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 20));
}

describe("sign-out across tabs", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("announces the sign-out to the other tabs", async () => {
    const tab = otherTab();
    const received: unknown[] = [];
    tab.onmessage = (event) => received.push(event.data);

    clearBrowserStorage();
    await delivered();

    expect(received).toEqual(["signed-out"]);
    tab.close();
  });

  // CASA 6.6.1: an open tab still shows the previous user's data after a
  // logout elsewhere; it must drop what it stored and leave the page.
  it("clears this tab's sessionStorage and reloads on a sign-out elsewhere", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    window.sessionStorage.setItem("dashboard_metrics_overview", "{}");
    const stop = reloadWhenSignedOutElsewhere();
    const tab = otherTab();

    tab.postMessage("something-else");
    await delivered();
    expect(reload).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(1);

    tab.postMessage("signed-out");
    await delivered();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.length).toBe(0);

    stop();
    tab.postMessage("signed-out");
    await delivered();
    expect(reload).toHaveBeenCalledTimes(1);
    tab.close();
  });

  it("does not reload the tab that signed out", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    const stop = reloadWhenSignedOutElsewhere();

    clearBrowserStorage();
    await delivered();

    expect(reload).not.toHaveBeenCalled();
    stop();
  });
});
