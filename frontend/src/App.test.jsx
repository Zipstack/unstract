import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "./store/session-store";

const unsubscribe = vi.fn();
const signOutWhenSignedOutElsewhere = vi.fn(() => unsubscribe);

vi.mock("@v1", async (importOriginal) => ({
  ...(await importOriginal()),
  signOutWhenSignedOutElsewhere: (...args) =>
    signOutWhenSignedOutElsewhere(...args),
}));
// The routes and analytics are not under test; they need a backend.
vi.mock("./routes/Router.jsx", () => ({ Router: () => null }));
vi.mock("./PostHogPageviewTracker.js", () => ({ default: () => null }));

const { App } = await import("./App.jsx");

describe("App", () => {
  afterEach(() => {
    signOutWhenSignedOutElsewhere.mockClear();
    unsubscribe.mockClear();
    useSessionStore.getState().setSessionDetails({});
  });

  // CASA 6.6.1: a logout in another tab must reach this one.
  it("listens for sign-outs in other tabs while mounted", () => {
    const { unmount } = render(<App />);

    expect(signOutWhenSignedOutElsewhere).toHaveBeenCalledTimes(1);
    expect(unsubscribe).not.toHaveBeenCalled();

    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });

  // Only a tab known to be signed out stays on its page; an unknown session
  // (a v1 page, which does not load v0's session) signs out.
  it("reports this tab as signed out only when the session says so", () => {
    render(<App />);
    const [isSignedOut] = signOutWhenSignedOutElsewhere.mock.calls[0];
    const { setSessionDetails } = useSessionStore.getState();

    setSessionDetails({});
    expect(isSignedOut()).toBe(false);
    setSessionDetails({ isLoggedIn: true });
    expect(isSignedOut()).toBe(false);
    setSessionDetails({ isLoggedIn: false });
    expect(isSignedOut()).toBe(true);
  });
});
