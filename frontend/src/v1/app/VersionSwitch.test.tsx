import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setOldVersion } from "@v1/app/api";
import { DEMO_PAGES } from "@v1/app/registry/entries";
import { buildLiveRegistry, type LiveRegistry } from "@v1/app/registry/live";
import { oldVersionStorageKey } from "@v1/lib/oldVersion";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import { useEffect } from "react";
import {
  MemoryRouter,
  type NavigateFunction,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VersionSwitch } from "./VersionSwitch";

const demo = buildLiveRegistry({
  devRoutes: true,
  distribution: "oss",
  storage: null,
});
const empty: LiveRegistry = { pages: [], entries: [] };

/** Every pathname the router passes through, and a handle to navigate. */
let visited: string[] = [];
let navigate: NavigateFunction = () => undefined;

function Where() {
  const { pathname } = useLocation();
  navigate = useNavigate();
  useEffect(() => {
    visited.push(pathname);
  }, [pathname]);
  return <output data-testid="where">{pathname}</output>;
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
  path: string | string[],
  {
    registry = demo,
    userId = "7",
  }: { registry?: LiveRegistry; userId?: string | null } = {},
) {
  const entries = Array.isArray(path) ? path : [path];
  const view = (user: string | null) => (
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
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
  visited = [];
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

  it("a redirect replaces the history entry, so Back skips the v0 URL", async () => {
    renderAt(["/acme/start", "/acme/v0-demo"]);
    await screen.findByTestId("v1-demo");
    act(() => {
      navigate(-1);
    });
    expect(where()).toBe("/acme/start");
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

    // v0's "Switch to new version" control calls the public entry.
    act(() => {
      expect(setOldVersion(false)).toBe(true);
    });
    expect(where()).toBe("/acme/v1-demo-review");
    expect(await screen.findByTestId("v1-demo-review")).toBeTruthy();
    expect(window.localStorage.getItem(oldVersionStorageKey("7"))).toBeNull();
  });

  it("a stored old-version choice applies on load (re-login)", () => {
    window.localStorage.setItem(oldVersionStorageKey("7"), "true");
    renderAt("/acme/v1-demo-review");
    expect(where()).toBe("/acme/v0-demo-review");
    expect(screen.getByTestId("v0")).toBeTruthy();
  });

  it("on reload, applies the last user's choice before the session loads", () => {
    useOldVersionStore.setState({ userId: "7", oldVersion: true });
    renderAt("/acme/v1-demo-review", { userId: null });
    expect(where()).toBe("/acme/v0-demo-review");
    expect(screen.queryByTestId("v1-demo-review")).toBeNull();
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

  it("is per user: another user signing in never passes through the previous user's old version", async () => {
    window.localStorage.setItem(oldVersionStorageKey("7"), "true");
    useOldVersionStore.setState({ userId: "7", oldVersion: true });
    renderAt("/acme/v1-demo-review", { userId: "8" });
    expect(await screen.findByTestId("v1-demo-review")).toBeTruthy();
    expect(visited).not.toContain("/acme/v0-demo-review");
  });

  it("contains a v1 failure in its own boundary instead of unmounting the app", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const broken = { ...DEMO_PAGES[0], page: "DEMO-BROKEN" } as const;
    renderAt("/acme/v1-demo", {
      registry: { pages: [broken], entries: [broken] },
    });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    vi.restoreAllMocks();
  });
});
