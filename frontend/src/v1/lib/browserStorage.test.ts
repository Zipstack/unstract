import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearBrowserStorage,
  clearUserLocalStorage,
  signOutWhenSignedOutElsewhere,
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

/** The message a tab posts when it signs out. */
function signedOut(sentAt: number = Date.now()) {
  return { type: "signed-out", sentAt };
}

// No fixed waits: messages reach a receiver in the order they were posted, so
// once the listener has handled the last one, it has handled every earlier
// one. Each test waits for that and then counts what got past the filter.
describe("sign-out across tabs", () => {
  const cleanups: (() => void)[] = [];

  /** Mounts the listener in this tab; `isSignedOut` counts what reached it. */
  function listen(signedOutHere = false) {
    const isSignedOut = vi.fn(() => signedOutHere);
    cleanups.push(signOutWhenSignedOutElsewhere(isSignedOut));
    return isSignedOut;
  }

  function stubAssign() {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    return assign;
  }

  function tab(): BroadcastChannel {
    const channel = otherTab();
    cleanups.push(() => channel.close());
    return channel;
  }

  afterEach(() => {
    for (const cleanup of cleanups.splice(0)) {
      cleanup();
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("announces the sign-out to the other tabs", async () => {
    const other = tab();
    const received = new Promise((resolve) => {
      other.onmessage = (event) => resolve(event.data);
    });

    clearBrowserStorage();

    expect(await received).toEqual({
      type: "signed-out",
      sentAt: expect.any(Number),
    });
  });

  // CASA 6.6.1: an open tab still shows the previous user's data after a
  // logout elsewhere; it must drop what it stored and leave the page.
  // It signs out rather than reloading: the server may not have ended the
  // session yet when the message arrives.
  it("clears this tab's sessionStorage and signs it out on a sign-out elsewhere", async () => {
    const assign = stubAssign();
    window.sessionStorage.setItem("dashboard_metrics_overview", "{}");
    const isSignedOut = listen();
    const other = tab();

    other.postMessage("something-else");
    other.postMessage("signed-out");
    other.postMessage({ type: "something-else", sentAt: Date.now() });
    other.postMessage(signedOut());
    await vi.waitFor(() => expect(assign).toHaveBeenCalled());

    expect(isSignedOut).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("/api/v1/logout");
    expect(window.sessionStorage.length).toBe(0);
  });

  it("does nothing after unsubscribe", async () => {
    const stopped = vi.fn(() => true);
    signOutWhenSignedOutElsewhere(stopped)();
    // A listener mounted now shares the channel: once it has the message,
    // the stopped one would have had it too.
    const live = listen(true);

    tab().postMessage(signedOut());
    await vi.waitFor(() => expect(live).toHaveBeenCalled());

    expect(stopped).not.toHaveBeenCalled();
  });

  // Review finding: an anonymous share viewer or /landing has no session to
  // end; sending it through the identity provider's logout loses the page.
  it("only clears sessionStorage in a tab known to be signed out", async () => {
    const assign = stubAssign();
    window.sessionStorage.setItem("dashboard_metrics_overview", "{}");
    const isSignedOut = listen(true);

    tab().postMessage(signedOut());
    await vi.waitFor(() => expect(isSignedOut).toHaveBeenCalled());

    expect(assign).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);
  });

  // Review finding: a frozen tab runs a queued message when it thaws. If
  // someone signed in again meanwhile, acting on it would end the new session.
  it("ignores a stale sign-out", async () => {
    const assign = stubAssign();
    const isSignedOut = listen();
    const other = tab();

    other.postMessage(signedOut(Date.now() - 60_000));
    other.postMessage(signedOut());
    await vi.waitFor(() => expect(assign).toHaveBeenCalled());

    expect(isSignedOut).toHaveBeenCalledTimes(1);
  });

  it("still signs out when this tab's storage is unavailable", async () => {
    const assign = stubAssign();
    vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    listen();

    tab().postMessage(signedOut());

    await vi.waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/api/v1/logout"),
    );
  });

  it("does not act on the tab's own sign-out", async () => {
    const isSignedOut = listen(true);

    clearBrowserStorage();
    // Posted after this tab's own message, so handled after it.
    tab().postMessage(signedOut());
    await vi.waitFor(() => expect(isSignedOut).toHaveBeenCalled());

    expect(isSignedOut).toHaveBeenCalledTimes(1);
  });
});
