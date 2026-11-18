import { screen } from "@testing-library/react";
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

const ORG = DEFAULT_SESSION.organization.id;
const member = makeSession({ role: "user" });

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
  { route = `/${ORG}/page`, wrap = (ui: ReactNode) => ui } = {},
) {
  const page = access === "guest" ? <p>guest page</p> : <Page />;
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
    expect(currentOrganizationId()).toBe(ORG);
    expect(useOldVersionStore.getState().userId).toBe(member.user.id);
  });

  it("shows the no-permission state to a member on an admin page", async () => {
    mockApi(...sessionHandlers(member));
    const { container } = renderGate("admin");
    expect(
      await screen.findByRole("heading", {
        name: "You don't have access to this page",
      }),
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
      await screen.findByRole("heading", {
        name: "You don't have access to this page",
      }),
    ).toBeInTheDocument();
  });

  it("sends a URL naming another organisation to organisation selection", async () => {
    mockApi(...sessionHandlers(member));
    renderGate("authenticated", { route: "/someone-else/page" });
    const { at, state } = await landed();
    expect(at).toBe("/setOrg");
    expect(state).toEqual([organizationRow(member)]);
  });

  it("sends a user with several organisations and none current to selection", async () => {
    const organizations = [
      organizationRow(member),
      organizationRow(makeSession({ organization: { id: "org-2" } })),
    ];
    mockApi(...sessionHandlers(member, { current: null, organizations }));
    renderGate("authenticated");
    const { at, state } = await landed();
    expect(at).toBe("/setOrg");
    expect(state).toEqual(organizations);
  });

  it("sends an ended session (412) to v0's error page with its cause", async () => {
    mockApi(
      http.get("/api/v1/organization", () =>
        HttpResponse.json({ code: "USR", domain: "acme.com" }, { status: 412 }),
      ),
      ...sessionHandlers(member),
    );
    renderGate("authenticated");
    expect((await landed()).at).toBe("/error?code=USR&domain=acme.com");
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
    const manifest: PluginManifest = {
      id: "gates",
      distributions: ["cloud"],
      slots: {
        "route.entitlement": async () => ({
          default: ({ children }) => <section>entitled: {children}</section>,
        }),
        "route.platform-admin": async () => ({
          default: ({ children }) => (
            <section>platform admin: {children}</section>
          ),
        }),
      },
    };
    const slot = makeSlot(buildRegistry([manifest], "cloud"), vi.fn());
    const wrap = (ui: ReactNode) => (
      <PluginProvider slot={slot}>{ui}</PluginProvider>
    );
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
});
