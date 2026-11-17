/*
 * RequireGuest on an OSS-ONLY build — no plugins directory, so no product
 * store at all.
 *
 * UN-4626 made this component read `?selectedProduct=` as a fallback when the
 * store cannot name an external home, which is what lets a visitor handed
 * here by another app reach the product they asked for instead of falling
 * through to Document Studio. The plugin that answers that question is
 * overlay-only: `frontend/src/plugins/` does not exist in this repository, so
 * the fallback's own behaviour is pinned by the cloud store's tests
 * (`externalHomeForProduct`) and by staging.
 *
 * What IS testable here, and what these tests are for, is the other half of
 * that contract: with no plugin present the new code path must be inert. The
 * query is read inside the same `try` that the absent import already throws
 * from, so an OSS build must route exactly as it did before — and must not
 * start throwing because a URL happens to carry the parameter.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: {
      isLoggedIn: true,
      orgName: "my-org",
      adapters: ["llm", "vector_db", "embedding", "x2text"],
    },
  }),
}));

const { RequireGuest } = await import("./RequireGuest.jsx");

const renderAt = (url) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route element={<RequireGuest />}>
          <Route path="/landing" element={<div>landing</div>} />
        </Route>
        <Route path="/my-org/*" element={<div>in-app</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe("RequireGuest without the product plugin (OSS build)", () => {
  it("routes a signed-in visitor in-app, parameter or not", async () => {
    renderAt("/landing?selectedProduct=flow");

    // Unchanged from before UN-4626: with no plugin there is no external home
    // to find, so the in-app destination still wins. An OSS deployment has
    // nowhere else to send anybody.
    expect(await screen.findByText("in-app")).toBeInTheDocument();
  });

  it("does not throw on a parameter it cannot resolve", async () => {
    // The fallback runs inside the same `try` the absent plugin import throws
    // from, so a malformed or hostile value must be swallowed exactly as the
    // missing plugin is — not surface as a render error on a sign-in route.
    renderAt("/landing?selectedProduct=https%3A%2F%2Fevil.example");

    expect(await screen.findByText("in-app")).toBeInTheDocument();
  });

  it("still shows the guest route to a visitor with no session", async () => {
    vi.resetModules();
    vi.doMock("../../../store/session-store", () => ({
      useSessionStore: () => ({ sessionDetails: { isLoggedIn: false } }),
    }));
    const { RequireGuest: Guest } = await import("./RequireGuest.jsx");

    render(
      <MemoryRouter initialEntries={["/landing?selectedProduct=flow"]}>
        <Routes>
          <Route element={<Guest />}>
            <Route path="/landing" element={<div>landing</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    // The branch this change must never disturb: `/landing` is a public route,
    // so a guest sees it. This is the path bug 1's bounce depends on.
    expect(await screen.findByText("landing")).toBeInTheDocument();
  });
});
