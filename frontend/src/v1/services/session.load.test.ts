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
import { ApiError } from "./errors";
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

  it("enters the session's organisation, not the first, when the user has several", async () => {
    const seen: string[] = [];
    const organizations = [
      organizationRow(DEFAULT_SESSION),
      organizationRow(other),
    ];
    mockApi(...sessionHandlers(other, { organizations, seen }));
    const load = await loadSession();
    if (load.kind !== "signed-in") {
      throw new Error(`expected signed-in, got ${load.kind}`);
    }
    expect(load.session.organization.id).toBe(other.organization.id);
    expect(seen).toContain(
      `POST /api/v1/organization/${other.organization.id}/set`,
    );
    expect(seen).not.toContain(`POST /api/v1/organization/${ORG}/set`);
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

  it("reports access removed, setting none, when the session's organisation is gone and several remain", async () => {
    const seen: string[] = [];
    const organizations = [
      organizationRow(DEFAULT_SESSION),
      organizationRow(other),
    ];
    mockApi(
      ...sessionHandlers(DEFAULT_SESSION, {
        current: "gone",
        organizations,
        seen,
      }),
    );
    expect(await loadSession()).toEqual({ kind: "access-removed" });
    expect(seen.some((call) => call.startsWith("POST"))).toBe(false);
  });

  it("reports access removed when the set call answers 403", async () => {
    mockApi(
      http.post("/api/v1/organization/:id/set", () =>
        HttpResponse.json({}, { status: 403 }),
      ),
      ...sessionHandlers(DEFAULT_SESSION),
    );
    expect(await loadSession()).toEqual({ kind: "access-removed" });
  });

  it("rejects with the set call's own ApiError, request id included, when set fails", async () => {
    mockApi(
      http.post("/api/v1/organization/:id/set", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
      ...sessionHandlers(DEFAULT_SESSION),
    );
    const error = await loadSession().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      kind: "server",
      status: 500,
      requestId: expect.any(String),
    });
  });

  it("reports a user with no organisation, rather than signing them out", async () => {
    mockApi(...sessionHandlers(DEFAULT_SESSION, { organizations: [] }));
    expect(await loadSession()).toEqual({ kind: "no-organization" });
  });

  it("sends the session probe a cache-buster each time, as v0 does", async () => {
    const busters: (string | null)[] = [];
    mockApi(
      http.get("/api/v1/session", ({ request }) => {
        busters.push(new URL(request.url).searchParams.get("q"));
        return HttpResponse.json({}, { status: 401 });
      }),
    );
    await loadSession();
    await new Promise((resolve) => setTimeout(resolve, 2));
    await loadSession();
    expect(busters).toHaveLength(2);
    expect(busters[0]).toMatch(/^\d+$/);
    expect(busters[1]).not.toBe(busters[0]);
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
