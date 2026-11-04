import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { buildLiveRegistry, type LiveRegistry } from "@v1/app/registry/live";
import { oldVersionStorageKey } from "@v1/lib/oldVersion";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { VersionSwitch } from "./VersionSwitch";

const demo = buildLiveRegistry({
  devRoutes: true,
  distribution: "oss",
  storage: null,
});
const empty: LiveRegistry = { pages: [], entries: [] };

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

/** Stands in for v0's routes. */
const v0 = (
  <Routes>
    <Route path="/:orgName/v0-demo" element={<p data-testid="v0">v0 demo</p>} />
    <Route
      path="/:orgName/v0-demo-review"
      element={<p data-testid="v0">v0 review</p>}
    />
    <Route path="*" element={<p data-testid="v0">v0 other</p>} />
  </Routes>
);

function renderAt(
  path: string,
  {
    registry = demo,
    userId = "7",
  }: { registry?: LiveRegistry; userId?: string | null } = {},
) {
  const view = (user: string | null) => (
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <VersionSwitch registry={registry} userId={user}>
        {v0}
      </VersionSwitch>
    </MemoryRouter>
  );
  const result = render(view(userId));
  return {
    ...result,
    setUser: (user: string | null) => result.rerender(view(user)),
  };
}

const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  window.localStorage.clear();
  useOldVersionStore.setState({ userId: null, oldVersion: null, chosen: {} });
});

describe("VersionSwitch", () => {
  it("with an empty registry renders v0 for every URL, including v0 URLs of demo pages", () => {
    for (const path of ["/acme/v0-demo", "/acme/v1-demo", "/acme/workflows"]) {
      const { unmount } = renderAt(path, { registry: empty });
      expect(screen.getByTestId("v0")).toBeTruthy();
      expect(where()).toBe(path);
      unmount();
    }
  });

  it("renders v0 for an unregistered URL", () => {
    renderAt("/acme/workflows");
    expect(screen.getByTestId("v0").textContent).toBe("v0 other");
  });

  it("renders a registered page as its own v1 tree, and redirects its v0 URL there", async () => {
    renderAt("/acme/v0-demo?x=1");
    expect(await screen.findByTestId("v1-demo")).toBeTruthy();
    expect(where()).toBe("/acme/v1-demo");
    expect(screen.queryByTestId("v0")).toBeNull();
    expect(
      screen.getByTestId("v1-demo").closest("[data-ui-version='v1']"),
    ).not.toBeNull();
  });

  it("Human Review round trip: old version maps to v0 and back, with no reload", async () => {
    const user = userEvent.setup();
    renderAt("/acme/v1-demo-review/details");
    await user.click(
      await screen.findByRole("button", { name: "Switch to old version" }),
    );

    // The v1-only sub-route lands on its nearest v0 route.
    expect(where()).toBe("/acme/v0-demo-review");
    expect(screen.getByTestId("v0").textContent).toBe("v0 review");
    expect(window.localStorage.getItem(oldVersionStorageKey("7"))).toBe("true");

    act(() => {
      useOldVersionStore.getState().setOldVersion(false);
    });
    expect(where()).toBe("/acme/v1-demo-review");
    expect(await screen.findByTestId("v1-demo-review")).toBeTruthy();
    expect(window.localStorage.getItem(oldVersionStorageKey("7"))).toBeNull();
  });

  it("a stored old-version choice applies on load (reload, re-login)", () => {
    window.localStorage.setItem(oldVersionStorageKey("7"), "true");
    renderAt("/acme/v1-demo-review");
    expect(where()).toBe("/acme/v0-demo-review");
    expect(screen.getByTestId("v0")).toBeTruthy();
  });

  it("the preference does nothing on a page without the toggle", async () => {
    window.localStorage.setItem(oldVersionStorageKey("7"), "true");
    renderAt("/acme/v0-demo");
    expect(await screen.findByTestId("v1-demo")).toBeTruthy();
  });

  it("keeps Human Review's v0 URL on v0 until the user is known, then applies their choice", async () => {
    const { setUser } = renderAt("/acme/v0-demo-review", { userId: null });
    expect(screen.getByTestId("v0")).toBeTruthy();
    expect(where()).toBe("/acme/v0-demo-review");

    setUser("7");
    expect(await screen.findByTestId("v1-demo-review")).toBeTruthy();
    expect(where()).toBe("/acme/v1-demo-review");
  });

  it("is per user: another user signing in does not inherit the old version", async () => {
    window.localStorage.setItem(oldVersionStorageKey("7"), "true");
    useOldVersionStore.setState({ userId: "7", oldVersion: true });
    renderAt("/acme/v0-demo-review", { userId: "8" });
    expect(await screen.findByTestId("v1-demo-review")).toBeTruthy();
  });
});
