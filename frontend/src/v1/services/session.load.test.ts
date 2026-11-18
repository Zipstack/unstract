import {
  DEFAULT_SESSION,
  HttpResponse,
  http,
  makeSession,
  mockApi,
  toV1Session,
} from "@v1/test";
import {
  guestHandlers,
  organizationRow,
  sessionHandlers,
} from "@v1/test/fixtures/session";
import { describe, expect, it, vi } from "vitest";
import { onSessionExpired } from "./context";
import { loadSession } from "./session";

const other = makeSession({
  organization: { id: "org-2", name: "Other", urlName: "other" },
});
const ORG = DEFAULT_SESSION.organization.id;

describe("loadSession", () => {
  it("is a guest on the session's 401, without signing anyone out", async () => {
    const expired = vi.fn();
    const cleanup = onSessionExpired(expired);
    mockApi(...guestHandlers());
    expect(await loadSession()).toEqual({ kind: "guest" });
    cleanup();
    expect(expired).not.toHaveBeenCalled();
  });

  it("loads the user and sets their current organisation again, by id, as v0 does on every load", async () => {
    const seen: string[] = [];
    mockApi(...sessionHandlers(DEFAULT_SESSION, { seen }));
    expect(await loadSession()).toEqual({
      kind: "signed-in",
      session: toV1Session(DEFAULT_SESSION),
      organizations: [organizationRow(DEFAULT_SESSION)],
    });
    expect(seen).toEqual([
      "GET /api/v1/session",
      "GET /api/v1/organization",
      `POST /api/v1/organization/${ORG}/set`,
      `GET /api/v1/unstract/${ORG}/users/profile/`,
    ]);
  });

  it("keeps the organisation's id and URL name apart, and reads staff", async () => {
    mockApi(...sessionHandlers(DEFAULT_SESSION, { isStaff: true }));
    const load = await loadSession();
    if (load.kind !== "signed-in") {
      throw new Error(`expected signed-in, got ${load.kind}`);
    }
    expect(load.session.organization).toMatchObject({
      id: ORG,
      name: DEFAULT_SESSION.organization.urlName,
    });
    expect(load.session.user.isStaff).toBe(true);
  });

  it("sets the only organisation when the session has none", async () => {
    const seen: string[] = [];
    mockApi(...sessionHandlers(DEFAULT_SESSION, { current: null, seen }));
    const load = await loadSession();
    expect(load.kind).toBe("signed-in");
    expect(seen).toContain(`POST /api/v1/organization/${ORG}/set`);
  });

  it("sets the only organisation when the session's is no longer the user's", async () => {
    const seen: string[] = [];
    mockApi(...sessionHandlers(DEFAULT_SESSION, { current: "gone", seen }));
    expect((await loadSession()).kind).toBe("signed-in");
    expect(seen).toContain(`POST /api/v1/organization/${ORG}/set`);
  });

  it("asks the user to choose among several when none is current", async () => {
    const organizations = [
      organizationRow(DEFAULT_SESSION),
      organizationRow(other),
    ];
    mockApi(
      ...sessionHandlers(DEFAULT_SESSION, { current: null, organizations }),
    );
    expect(await loadSession()).toEqual({
      kind: "choose-organization",
      organizations,
    });
  });

  it("treats a user with no organisation as signed out, as v0 does", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    mockApi(...sessionHandlers(DEFAULT_SESSION, { organizations: [] }));
    expect(await loadSession()).toEqual({ kind: "guest" });
  });

  it("reports an ended session (412) with its cause", async () => {
    const body = { code: "USR", domain: "acme.com" };
    mockApi(
      http.get("/api/v1/organization", () =>
        HttpResponse.json(body, { status: 412 }),
      ),
      ...sessionHandlers(DEFAULT_SESSION),
    );
    expect(await loadSession()).toEqual({ kind: "ended", body });
  });

  it.each([
    ["the session", "/api/v1/session", { html: true }],
    ["the profile", "/api/v1/unstract/:org/users/profile/", {}],
  ])("rejects when %s reply is not one", async (_, path, body) => {
    mockApi(
      http.get(path, () => HttpResponse.json(body)),
      ...sessionHandlers(DEFAULT_SESSION),
    );
    await expect(loadSession()).rejects.toThrow(/carried no user/);
  });

  it("rejects with the ApiError when the session call fails", async () => {
    mockApi(
      http.get("/api/v1/session", () => HttpResponse.json({}, { status: 500 })),
    );
    await expect(loadSession()).rejects.toMatchObject({ kind: "server" });
  });
});
