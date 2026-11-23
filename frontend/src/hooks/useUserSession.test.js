import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const axiosMock = vi.fn();
vi.mock("axios", () => ({ default: (...args) => axiosMock(...args) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../hooks/useExceptionHandler.jsx", () => ({
  useExceptionHandler: () => () => ({}),
}));

const { useUserSession } = await import("./useUserSession.js");
const { getCached, setCache } = await import("../helpers/metricsCache.js");

describe("useUserSession", () => {
  afterEach(() => {
    axiosMock.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  // CASA 6.6.1: a session that ended without a logout (expiry) must not leave
  // the last user's data in localStorage for the next person on the browser.
  it("clears the user's localStorage when the server reports no session", async () => {
    axiosMock.mockRejectedValue({
      response: { data: { message: "Unauthorized" } },
    });
    window.localStorage.setItem("oauth-cachekey-google_drive", "cache-key");
    window.localStorage.setItem("selectedProduct", "unstract");
    window.sessionStorage.setItem("unstract:silentSignInAt", "1");

    const { result } = renderHook(() => useUserSession());
    const session = await result.current();

    expect(session).toBeUndefined();
    expect(
      window.localStorage.getItem("oauth-cachekey-google_drive"),
    ).toBeNull();
    expect(window.localStorage.getItem("selectedProduct")).toBe("unstract");
    expect(window.sessionStorage.getItem("unstract:silentSignInAt")).toBe("1");
  });

  // The org's dashboard metrics are cached in sessionStorage. A session that
  // expired, or a reply that landed after logout, must not leave them for the
  // next sign-in in this tab. This also runs on /landing after every logout.
  it("drops the tab's cached dashboard metrics when the server reports no session", async () => {
    axiosMock.mockRejectedValue({
      response: { data: { message: "Unauthorized" } },
    });
    setCache("overview", { org: "org_1" }, { total: 3 });
    window.sessionStorage.setItem("unstract:silentSignInAt", "1");

    const { result } = renderHook(() => useUserSession());
    await result.current();

    expect(
      Object.keys(window.sessionStorage).filter((key) =>
        key.startsWith("dashboard_metrics_"),
      ),
    ).toEqual([]);
    expect(window.sessionStorage.getItem("unstract:silentSignInAt")).toBe("1");
  });

  it.each([
    ["a 502", { response: { status: 502, data: {} } }],
    [
      "an ended subscription",
      { response: { status: 403, data: { type: "subscription_error" } } },
    ],
  ])("keeps stored data when the session request fails with %s", async (_, error) => {
    axiosMock.mockRejectedValue(error);
    window.localStorage.setItem("oauth-cachekey-google_drive", "cache-key");
    setCache("overview", { org: "org_1" }, { total: 3 });

    const { result } = renderHook(() => useUserSession());
    await result.current();

    expect(window.localStorage.getItem("oauth-cachekey-google_drive")).toBe(
      "cache-key",
    );
    expect(getCached("overview", { org: "org_1" })).toEqual({ total: 3 });
  });
});
