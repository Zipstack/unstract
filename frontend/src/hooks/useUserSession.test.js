import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const axiosMock = vi.fn();
vi.mock("axios", () => ({ default: (...args) => axiosMock(...args) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../hooks/useExceptionHandler.jsx", () => ({
  useExceptionHandler: () => () => ({}),
}));

const { useUserSession } = await import("./useUserSession.js");

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
    window.localStorage.setItem("dashboard_metrics_overview", '{"data":{}}');
    window.localStorage.setItem("selectedProduct", "unstract");
    window.sessionStorage.setItem("unstract:silentSignInAt", "1");

    const { result } = renderHook(() => useUserSession());
    const session = await result.current();

    expect(session).toBeUndefined();
    expect(
      window.localStorage.getItem("dashboard_metrics_overview"),
    ).toBeNull();
    expect(window.localStorage.getItem("selectedProduct")).toBe("unstract");
    expect(window.sessionStorage.getItem("unstract:silentSignInAt")).toBe("1");
  });

  it("keeps localStorage when the session request fails for another reason", async () => {
    axiosMock.mockRejectedValue({ response: { status: 502, data: {} } });
    window.localStorage.setItem("dashboard_metrics_overview", '{"data":{}}');

    const { result } = renderHook(() => useUserSession());
    await result.current();

    expect(window.localStorage.getItem("dashboard_metrics_overview")).toBe(
      '{"data":{}}',
    );
  });
});
