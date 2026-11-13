import { delay, HttpResponse, http as mock, mockApi } from "@v1/test";
import { isCancel } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onSessionExpired, setOrganizationId } from "./context";
import { ApiError, REQUEST_ID_HEADER } from "./errors";
import { createHttpClient, http, orgPath } from "./http";

const URL = "/api/v1/echo/";
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

type Echo = { csrf: string | null; requestId: string | null };

function mockEcho(): void {
  mockApi(
    mock.all(URL, ({ request }) =>
      HttpResponse.json<Echo>({
        csrf: request.headers.get("X-CSRFToken"),
        requestId: request.headers.get(REQUEST_ID_HEADER),
      }),
    ),
  );
}

/* The browser's cookie string, as the client reads it. */
function setCookies(cookies: string): void {
  vi.spyOn(document, "cookie", "get").mockReturnValue(cookies);
}

describe("orgPath", () => {
  afterEach(() => setOrganizationId(null));

  it("builds the org-scoped path and keeps the trailing slash as written", () => {
    setOrganizationId("org-1");
    expect(orgPath("/adapter/")).toBe("/api/v1/unstract/org-1/adapter/");
    expect(orgPath("/adapter/info/a1/")).toBe(
      "/api/v1/unstract/org-1/adapter/info/a1/",
    );
    expect(orgPath("/flags")).toBe("/api/v1/unstract/org-1/flags");
  });

  it("uses the organisation given, else the current one", () => {
    setOrganizationId("org-1");
    expect(orgPath("/x/", "org-2")).toBe("/api/v1/unstract/org-2/x/");
    expect(orgPath("/x/", undefined)).toBe("/api/v1/unstract/org-1/x/");
  });

  it("encodes the organisation id, so it stays one segment", () => {
    setOrganizationId("a/b c");
    expect(orgPath("/x/")).toBe("/api/v1/unstract/a%2Fb%20c/x/");
  });

  it("throws while no organisation is set", () => {
    expect(() => orgPath("/adapter/")).toThrow(/No organisation is set/);
  });
});

describe("CSRF header", () => {
  beforeEach(() => {
    setCookies("sessionid=s1; csrftoken=tok-123; theme=dark");
    mockEcho();
  });

  it.each([
    "post",
    "put",
    "patch",
    "delete",
  ] as const)("is sent on %s", async (method) => {
    const { data } = await http.request<Echo>({ url: URL, method });
    expect(data.csrf).toBe("tok-123");
  });

  it("is not sent to another origin", async () => {
    const other = "https://other.example/api/v1/echo/";
    mockApi(
      mock.post(other, ({ request }) =>
        HttpResponse.json<Echo>({
          csrf: request.headers.get("X-CSRFToken"),
          requestId: null,
        }),
      ),
    );
    const { data } = await http.post<Echo>(other);
    expect(data.csrf).toBeNull();
  });

  it("is not sent on get", async () => {
    const { data } = await http.get<Echo>(URL);
    expect(data.csrf).toBeNull();
  });

  it("is not sent when there is no csrftoken cookie, or it is malformed", async () => {
    setCookies("sessionid=s1");
    expect((await http.post<Echo>(URL)).data.csrf).toBeNull();
    setCookies("csrftoken=%E0%A4%A");
    expect((await http.post<Echo>(URL)).data.csrf).toBeNull();
  });
});

describe("request id header", () => {
  beforeEach(mockEcho);

  it("is a new UUID on every request", async () => {
    const first = (await http.get<Echo>(URL)).data.requestId;
    const second = (await http.get<Echo>(URL)).data.requestId;
    expect(first).toMatch(UUID_V4);
    expect(second).toMatch(UUID_V4);
    expect(first).not.toBe(second);
  });

  it("is a UUID outside a secure context, where randomUUID is missing", async () => {
    const { getRandomValues } = crypto;
    vi.stubGlobal("crypto", { getRandomValues: getRandomValues.bind(crypto) });
    const { data } = await http.get<Echo>(URL);
    expect(data.requestId).toMatch(UUID_V4);
  });

  it("keeps an id the caller set", async () => {
    const headers = { [REQUEST_ID_HEADER]: "mine" };
    const { data } = await http.get<Echo>(URL, { headers });
    expect(data.requestId).toBe("mine");
  });
});

describe("failures", () => {
  it("reject with an ApiError carrying the request id that was sent", async () => {
    mockApi(mock.get(URL, () => HttpResponse.text("boom", { status: 500 })));
    const headers = { [REQUEST_ID_HEADER]: "sent-1" };
    const error = await http.get(URL, { headers }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "server", requestId: "sent-1" });
  });
});

describe("401", () => {
  it("expires the session once for concurrent 401s, and rejects each", async () => {
    mockApi(
      mock.get(URL, () =>
        HttpResponse.json({ message: "Unauthorized" }, { status: 401 }),
      ),
    );
    const expired = vi.fn();
    const cleanup = onSessionExpired(expired);
    const client = createHttpClient();
    const results = await Promise.allSettled([
      client.get(URL),
      client.get(URL),
    ]);
    cleanup();
    expect(expired).toHaveBeenCalledTimes(1);
    for (const result of results) {
      expect(result).toMatchObject({
        status: "rejected",
        reason: { kind: "unauthenticated" },
      });
    }
  });

  it("expires the session once per page load: the handler leaves the page", async () => {
    mockApi(
      mock.get(URL, () =>
        HttpResponse.json({ message: "Unauthorized" }, { status: 401 }),
      ),
    );
    const expired = vi.fn();
    const cleanup = onSessionExpired(expired);
    const client = createHttpClient();
    const first = await client.get(URL).catch((e: unknown) => e);
    const second = await client.get(URL).catch((e: unknown) => e);
    cleanup();
    expect(expired).toHaveBeenCalledTimes(1);
    expect(first).toMatchObject({ kind: "unauthenticated" });
    expect(second).toMatchObject({ kind: "unauthenticated" });
  });

  it("is not treated as expiry for other statuses", async () => {
    mockApi(mock.get(URL, () => HttpResponse.json({}, { status: 403 })));
    const expired = vi.fn();
    const cleanup = onSessionExpired(expired);
    await createHttpClient()
      .get(URL)
      .catch(() => undefined);
    cleanup();
    expect(expired).not.toHaveBeenCalled();
  });
});

describe("cancellation", () => {
  it("rejects as cancelled, not as an ApiError, when the signal aborts", async () => {
    mockApi(
      mock.get(URL, async () => {
        await delay(50);
        return HttpResponse.json({});
      }),
    );
    const expired = vi.fn();
    const cleanup = onSessionExpired(expired);
    const controller = new AbortController();
    const pending = http.get(URL, { signal: controller.signal });
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    cleanup();
    expect(isCancel(error)).toBe(true);
    expect(error).not.toBeInstanceOf(ApiError);
    expect(expired).not.toHaveBeenCalled();
  });
});
