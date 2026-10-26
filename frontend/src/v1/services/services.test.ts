import { http } from "@v1/lib/http";
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { listOrganizations, switchOrganization } from "./organizations";
import { signOut } from "./session";

const sent: AxiosRequestConfig[] = [];
let reply: { status: number; data: unknown };

beforeEach(() => {
  sent.length = 0;
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

describe("signOut", () => {
  test("posts to logout with the CSRF token and returns where to go", async () => {
    reply.data = { redirect_url: "https://id.example.com/v2/logout" };
    await expect(signOut()).resolves.toBe("https://id.example.com/v2/logout");
    expect(sent[0]).toMatchObject({ method: "post", url: "/api/v1/logout" });
    expect(sent[0].headers?.["X-CSRFToken"]).toBe("tok123");
  });
});
