import { http } from "@v1/lib/http";
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { listOrganizations, switchOrganization } from "./organizations";
import { signOut, signOutAndLeave } from "./session";

const reset = vi.fn();
vi.mock("posthog-js", () => ({ default: { reset: () => reset() } }));

const sent: AxiosRequestConfig[] = [];
let reply: { status: number; data: unknown };

beforeEach(() => {
  sent.length = 0;
  reset.mockReset();
  reply = { status: 200, data: {} };
  http.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    sent.push(config);
    const response = { ...reply, statusText: "", headers: {}, config };
    if (reply.status >= 400) {
      throw Object.assign(new Error(`HTTP ${reply.status}`), { response });
    }
    return response;
  };
  // biome-ignore lint/suspicious/noDocumentCookie: the client reads this cookie
  document.cookie = "csrftoken=tok123";
});

afterEach(() => {
  // biome-ignore lint/suspicious/noDocumentCookie: clears the cookie set above
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.unstubAllGlobals();
});

describe("organizations", () => {
  test("lists the user's organisations", async () => {
    reply.data = {
      organizations: [
        {
          id: "org_1",
          name: "zipstack",
          display_name: "Zipstack",
          role: "admin",
        },
      ],
    };
    await expect(listOrganizations()).resolves.toEqual([
      {
        id: "org_1",
        name: "zipstack",
        display_name: "Zipstack",
        role: "admin",
      },
    ]);
    expect(sent[0]).toMatchObject({
      method: "get",
      url: "/api/v1/organization",
    });
    expect(sent[0].headers?.["X-CSRFToken"]).toBeUndefined();
  });

  test("switching posts to the organisation's set endpoint with the CSRF token", async () => {
    await switchOrganization("org/1");
    expect(sent[0]).toMatchObject({
      method: "post",
      url: "/api/v1/organization/org%2F1/set",
    });
    expect(sent[0].headers?.["X-CSRFToken"]).toBe("tok123");
  });

  test("a failed request rejects instead of resolving empty", async () => {
    reply = { status: 500, data: {} };
    await expect(listOrganizations()).rejects.toThrow("HTTP 500");
  });
});

describe("http CSRF cookie", () => {
  test("a malformed cookie sends no header instead of throwing", async () => {
    // biome-ignore lint/suspicious/noDocumentCookie: sets a cookie that cannot be decoded
    document.cookie = "csrftoken=%E0%A4%A";
    await expect(switchOrganization("org_1")).resolves.toBeUndefined();
    expect(sent[0].headers?.["X-CSRFToken"]).toBeUndefined();
  });

  test("a missing cookie sends no header", async () => {
    // biome-ignore lint/suspicious/noDocumentCookie: clears the cookie set in beforeEach
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    await switchOrganization("org_1");
    expect(sent[0].headers?.["X-CSRFToken"]).toBeUndefined();
  });
});

describe("signOut", () => {
  test("posts to logout with the CSRF token and returns where to go", async () => {
    reply.data = { redirect_url: "https://id.example.com/v2/logout" };
    await expect(signOut()).resolves.toBe("https://id.example.com/v2/logout");
    expect(sent[0]).toMatchObject({ method: "post", url: "/api/v1/logout" });
    expect(sent[0].headers?.["X-CSRFToken"]).toBe("tok123");
  });

  test("a reply without a redirect URL is an error, not /undefined", async () => {
    reply.data = {};
    await expect(signOut()).rejects.toThrow();
    reply.data = { redirect_url: "" };
    await expect(signOut()).rejects.toThrow();
  });
});

describe("signOutAndLeave", () => {
  const assign = vi.fn();
  beforeEach(() => {
    assign.mockReset();
    vi.stubGlobal("location", { ...window.location, assign });
  });

  test("resets analytics and opens the returned URL", async () => {
    reply.data = { redirect_url: "https://id.example.com/v2/logout" };
    await signOutAndLeave();
    expect(reset).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("https://id.example.com/v2/logout");
  });

  test("a failed POST resets analytics and falls back to the GET logout", async () => {
    reply = { status: 403, data: {} };
    await signOutAndLeave();
    expect(reset).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("/api/v1/logout");
  });

  test("a reply without a redirect URL falls back to the GET logout", async () => {
    reply.data = {};
    await signOutAndLeave();
    expect(reset).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("/api/v1/logout");
    expect(assign).not.toHaveBeenCalledWith(undefined);
  });
});
