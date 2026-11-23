import { configure, render, screen } from "@testing-library/react";
import { DEMO_PAGES } from "@v1/app/registry/entries";
import { expireSession } from "@v1/services/context";
import {
  DEFAULT_SESSION,
  HttpResponse,
  http,
  makeSession,
  mockApi,
} from "@v1/test";
import { sessionHandlers } from "@v1/test/fixtures/session";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { V1App, v1QueryClient } from "./V1App";

vi.mock("posthog-js", () => ({ default: { reset: vi.fn(), __loaded: false } }));

// Core tests render without plugins, whatever the build's distribution.
vi.mock("@v1/plugins", async () => {
  const { buildRegistry, makeSlot } = await import("@v1/lib/plugins");
  return { PluginSlot: makeSlot(buildRegistry([], "oss"), () => undefined) };
});

// The session loads before the page, and the first v1 render loads its chunks: past findBy's 1 s default under coverage.
configure({ asyncUtilTimeout: 3000 });

const ORG = DEFAULT_SESSION.organization.urlName;

async function renderDemo() {
  mockApi(
    ...sessionHandlers(DEFAULT_SESSION),
    http.get("/api/v1/unstract/:org/adapter/", () => HttpResponse.json([])),
  );
  const view = render(
    <MemoryRouter initialEntries={[`/${ORG}/v1-demo`]}>
      <V1App entry={DEMO_PAGES[0]} />
    </MemoryRouter>,
  );
  await screen.findByTestId("v1-demo");
  return view;
}

beforeEach(() => v1QueryClient.clear());

describe("V1App session expiry", () => {
  it.each([
    ["answers with the sign-out URL", 200, "http://localhost:3000/landing"],
    ["fails", 500, "/api/v1/logout"],
  ])("leaves the page when the POST sign-out %s", async (_, status, target) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const assign = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => undefined);
    mockApi(
      http.post("/api/v1/logout", () =>
        HttpResponse.json({ redirect_url: "/landing" }, { status }),
      ),
    );
    const { unmount } = await renderDemo();
    expireSession();
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith(target));
    unmount();
  });
});

describe("V1App guards", () => {
  it("guards a page with its registry access", async () => {
    mockApi(...sessionHandlers(makeSession({ role: "user" })));
    render(
      <MemoryRouter initialEntries={[`/${ORG}/v1-demo`]}>
        <V1App entry={{ ...DEMO_PAGES[0], access: "admin" }} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "You don't have access to this page",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("v1-demo")).toBeNull();
  });
});
