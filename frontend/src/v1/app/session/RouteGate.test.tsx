import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { RouteAccess } from "@v1/app/registry/types";
import {
  buildRegistry,
  makeSlot,
  type PluginManifest,
  PluginProvider,
} from "@v1/lib/plugins";
import { useSession } from "@v1/lib/session";
import { currentOrganizationId } from "@v1/services/context";
import { useOldVersionStore } from "@v1/stores/oldVersion";
import {
  DEFAULT_SESSION,
  HttpResponse,
  http,
  makeSession,
  mockApi,
  renderV1,
  toV1Session,
} from "@v1/test";
import {
  guestHandlers,
  organizationRow,
  sessionHandlers,
} from "@v1/test/fixtures/session";
import type { ReactNode } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouteGate } from "./RouteGate";

const identify = vi.hoisted(() => vi.fn());
vi.mock("@v1/lib/analytics", () => ({ identifyUser: identify }));
const signOutAndLeave = vi.hoisted(() => vi.fn<() => Promise<void>>());
vi.mock("@v1/services/session", async (actual) => ({
  ...(await actual<typeof import("@v1/services/session")>()),
  signOutAndLeave,
}));

const ORG_ID = DEFAULT_SESSION.organization.id;
const ORG = DEFAULT_SESSION.organization.urlName;
const member = makeSession({ role: "user" });
const DENIED = "You don't have access to this page";

type Slots = PluginManifest["slots"];

/** A provider whose cloud gates are `slots`; `report` records plugin failures. */
function gates(slots: Slots, report = vi.fn()) {
  const manifest: PluginManifest = {
    id: "gates",
    distributions: ["cloud"],
    slots,
  };
  const slot = makeSlot(buildRegistry([manifest], "cloud"), report);
  return (ui: ReactNode) => <PluginProvider slot={slot}>{ui}</PluginProvider>;
}

const passThrough = (label: string) => async () => ({
  default: ({ children }: { children: ReactNode }) => (
    <section>
      {label}: {children}
    </section>
  ),
});

function Broken(): never {
  throw new Error("page bug");
}

function Page() {
  const { user, organization } = useSession();
  return (
    <p>
      page for {user.name} in {organization.displayName}
    </p>
  );
}

/** Where a redirect landed, and the state it carried. */
function Where() {
  const { pathname, search, state } = useLocation();
  return (
    <output data-testid="where" data-state={JSON.stringify(state)}>
      {pathname}
      {search}
    </output>
  );
}

function renderGate(
  access: RouteAccess,
  {
    route = `/${ORG}/page`,
    wrap = (ui: ReactNode) => ui,
    page = access === "guest" ? <p>guest page</p> : <Page />,
  }: {
    route?: string;
    wrap?: (ui: ReactNode) => ReactNode;
    page?: ReactNode;
  } = {},
) {
  const ui = (
    <Routes>
      <Route
        path="/:orgName/page"
        element={<RouteGate access={access}>{page}</RouteGate>}
      />
      <Route
        path="/sign-in-page"
        element={<RouteGate access={access}>{page}</RouteGate>}
      />
      <Route path="*" element={<Where />} />
    </Routes>
  );
  // No session from the harness: the gate loads its own.
  return renderV1(wrap(ui), { route, session: null });
}

const landed = async () => {
  const where = await screen.findByTestId("where");
  return {
    at: where.textContent,
    state: JSON.parse(where.dataset.state ?? "null"),
  };
};

beforeEach(() => {
  useOldVersionStore.setState({ userId: null, oldVersion: null, chosen: {} });
  signOutAndLeave.mockReset().mockResolvedValue();
});

describe("RouteGate", () => {
  it("sends a guest to sign in, remembering the URL", async () => {
    mockApi(...guestHandlers());
    renderGate("authenticated");
    const { at, state } = await landed();
    expect(at).toBe("/landing");
    expect(state.from.pathname).toBe(`/${ORG}/page`);
  });

  it("renders the page for a member, with the session, organisation and user applied", async () => {
    mockApi(...sessionHandlers(member));
    renderGate("authenticated");
    expect(
      await screen.findByText("page for Ada in Example Org"),
    ).toBeInTheDocument();
    expect(currentOrganizationId()).toBe(ORG_ID);
    expect(useOldVersionStore.getState().userId).toBe(member.user.id);
    expect(identify).toHaveBeenCalledWith(toV1Session(member));
  });

  it("checks the URL against the organisation's URL name, not its id", async () => {
    mockApi(...sessionHandlers(member));
    renderGate("authenticated", { route: `/${ORG_ID}/page` });
    expect((await landed()).at).toBe("/landing");
  });

  it("shows the no-permission state to a member on an admin page", async () => {
    mockApi(...sessionHandlers(member));
    const { container } = renderGate("admin");
    expect(
      await screen.findByRole("heading", { name: DENIED }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/page for/)).not.toBeInTheDocument();
    await expect(container).toHaveNoA11yViolations();
  });

  it("renders an admin page for an admin", async () => {
    mockApi(...sessionHandlers(DEFAULT_SESSION));
    renderGate("admin");
    expect(await screen.findByText(/page for Ada/)).toBeInTheDocument();
  });

  it("denies a platform-admin page when no cloud gate decides it", async () => {
    mockApi(...sessionHandlers(DEFAULT_SESSION));
    renderGate("platform-admin");
    expect(
      await screen.findByRole("heading", { name: DENIED }),
    ).toBeInTheDocument();
  });

  it("sends a URL naming another organisation to sign-in, which opens the current one", async () => {
    mockApi(...sessionHandlers(member));
    renderGate("authenticated", { route: "/someone-else/page" });
    const { at, state } = await landed();
    expect(at).toBe("/landing");
    expect(state).toBeNull();
  });

  it("sends a user with several organisations and none current to selection", async () => {
    const organizations = [
      organizationRow(member),
      organizationRow(
        makeSession({ organization: { id: "org-2", urlName: "other" } }),
      ),
    ];
    mockApi(...sessionHandlers(member, { current: null, organizations }));
    renderGate("authenticated");
    const { at, state } = await landed();
    expect(at).toBe("/setOrg");
    expect(state).toEqual(organizations);
  });

  it("sends an ended session (412) to v0's error page with its cause, by a full load", async () => {
    const replace = vi
      .spyOn(window.location, "replace")
      .mockImplementation(() => undefined);
    mockApi(
      http.get("/api/v1/organization", () =>
        HttpResponse.json({ code: "USR", domain: "acme.com" }, { status: 412 }),
      ),
      ...sessionHandlers(member),
    );
    renderGate("authenticated");
    await vi.waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/error?code=USR&domain=acme.com"),
    );
  });

  it.each([
    [
      "the session's organisation is gone and several remain",
      { current: "gone" },
      "You no longer have access to this organisation.",
    ],
    [
      "the user belongs to no organisation",
      { organizations: [] },
      "Your account does not belong to any organisation.",
    ],
  ])("offers sign-out when %s", async (_, options, message) => {
    const organizations = [
      organizationRow(member),
      organizationRow(
        makeSession({ organization: { id: "org-2", urlName: "other" } }),
      ),
    ];
    mockApi(...sessionHandlers(member, { organizations, ...options }));
    renderGate("authenticated");
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByTestId("where")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOutAndLeave).toHaveBeenCalledTimes(1);
    // Gone after one click, so a second sign-out cannot race the first.
    expect(
      screen.queryByRole("button", { name: "Sign out" }),
    ).not.toBeInTheDocument();
  });

  it("renders a guest page for a guest, and sends a signed-in user into the app", async () => {
    mockApi(...guestHandlers());
    const { unmount } = renderGate("guest", { route: "/sign-in-page" });
    expect(await screen.findByText("guest page")).toBeInTheDocument();
    unmount();
    mockApi(...sessionHandlers(member));
    renderGate("guest", { route: "/sign-in-page" });
    expect((await landed()).at).toBe("/landing");
  });

  it("shows a failed load inline with Retry", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    mockApi(
      http.get("/api/v1/session", () => HttpResponse.json({}, { status: 500 })),
    );
    renderGate("authenticated");
    expect(
      await screen.findByRole("button", { name: "Retry" }),
    ).toBeInTheDocument();
  });

  it("lets a cloud plugin gate every signed-in page, and decide platform-admin pages", async () => {
    mockApi(...sessionHandlers(member));
    const wrap = gates({
      "route.entitlement": passThrough("entitled"),
      "route.platform-admin": passThrough("platform admin"),
    });
    const { unmount } = renderGate("authenticated", { wrap });
    expect(await screen.findByText(/entitled:/)).toHaveTextContent(
      "entitled: page for Ada in Example Org",
    );
    unmount();
    renderGate("platform-admin", { wrap });
    const decided = await screen.findByText(/platform admin:/);
    expect(decided).toHaveTextContent("platform admin: page for Ada");
    expect(decided.parentElement).toHaveTextContent(
      /^entitled: platform admin/,
    );
  });

  it("keeps the page hidden while a gate's plugin loads", async () => {
    mockApi(...sessionHandlers(member));
    let release: () => void = () => undefined;
    const loaded = new Promise<void>((resolve) => {
      release = resolve;
    });
    const gate = passThrough("entitled");
    const started = vi.fn();
    const wrap = gates({
      "route.entitlement": async () => {
        started();
        await loaded;
        return gate();
      },
    });
    renderGate("authenticated", { wrap });
    await vi.waitFor(() => expect(started).toHaveBeenCalled());
    expect(screen.queryByText(/page for/)).not.toBeInTheDocument();
    release();
    expect(await screen.findByText(/entitled:/)).toBeInTheDocument();
  });

  it("keeps the page closed when a gate's plugin fails to load", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockApi(...sessionHandlers(member));
    const report = vi.fn();
    const wrap = gates(
      { "route.entitlement": () => Promise.reject(new Error("chunk gone")) },
      report,
    );
    renderGate("authenticated", { wrap });
    expect(
      await screen.findByText("This page could not be loaded."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/page for/)).not.toBeInTheDocument();
    expect(report).toHaveBeenCalledTimes(1);
  });

  it.each([
    "authenticated",
    "platform-admin",
  ] as const)("a %s page that throws is the page's error, not the gate plugin's", async (access) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockApi(...sessionHandlers(member));
    const report = vi.fn();
    const wrap = gates(
      {
        "route.entitlement": passThrough("entitled"),
        "route.platform-admin": passThrough("platform admin"),
      },
      report,
    );
    renderGate(access, { wrap, page: <Broken /> });
    expect(
      await screen.findByText("This page could not be loaded."),
    ).toBeInTheDocument();
    expect(screen.getByText(/entitled:/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: DENIED })).toBeNull();
    expect(report).not.toHaveBeenCalled();
  });
});
