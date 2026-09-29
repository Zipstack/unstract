import axios from "axios";
import Cookies from "js-cookie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../store/session-store";
import {
  attachCsrfInterceptor,
  CSRF_HEADER,
  getCsrfHeaders,
  getCsrfToken,
} from "./csrf";

const runRequestInterceptors = async (instance, config = {}) => {
  let current = { ...config, headers: { ...config.headers } };
  for (const handler of instance.interceptors.request.handlers) {
    if (handler?.fulfilled) {
      current = await handler.fulfilled(current);
    }
  }
  return current;
};

const withInterceptor = () => {
  const instance = axios.create();
  attachCsrfInterceptor(instance);
  return instance;
};

describe("csrf helpers", () => {
  beforeEach(() => {
    useSessionStore.setState({ sessionDetails: { csrfToken: "store-tok" } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useSessionStore.setState({ sessionDetails: {} });
  });

  describe("getCsrfToken", () => {
    it("prefers the session store", () => {
      vi.spyOn(Cookies, "get").mockReturnValue("cookie-tok");
      expect(getCsrfToken()).toBe("store-tok");
    });

    it("falls back to the csrftoken cookie before the session hydrates", () => {
      useSessionStore.setState({ sessionDetails: {} });
      const get = vi.spyOn(Cookies, "get").mockReturnValue("cookie-tok");
      expect(getCsrfToken()).toBe("cookie-tok");
      expect(get).toHaveBeenCalledWith("csrftoken");
    });
  });

  describe("attachCsrfInterceptor", () => {
    it.each([
      "post",
      "PUT",
      "patch",
      "delete",
    ])("sets the header on %s", async (method) => {
      const result = await runRequestInterceptors(withInterceptor(), {
        method,
        url: "/api/v1/unstract/org/items/",
      });
      expect(result.headers[CSRF_HEADER]).toBe("store-tok");
    });

    it.each([
      "get",
      "head",
      "options",
      undefined,
    ])("leaves safe method %s alone", async (method) => {
      const result = await runRequestInterceptors(withInterceptor(), {
        method,
        url: "/api/v1/unstract/org/items/",
      });
      expect(result.headers[CSRF_HEADER]).toBeUndefined();
    });

    it("does not send the token to another origin", async () => {
      const result = await runRequestInterceptors(withInterceptor(), {
        method: "post",
        url: "https://example.com/upload",
      });
      expect(result.headers[CSRF_HEADER]).toBeUndefined();
    });

    it("sends the token to an absolute same-origin URL", async () => {
      const result = await runRequestInterceptors(withInterceptor(), {
        method: "post",
        url: `${globalThis.location.origin}/api/v1/items/`,
      });
      expect(result.headers[CSRF_HEADER]).toBe("store-tok");
    });

    it("does not overwrite a caller-supplied token", async () => {
      const result = await runRequestInterceptors(withInterceptor(), {
        method: "post",
        url: "/api/v1/items/",
        headers: { [CSRF_HEADER]: "explicit" },
      });
      expect(result.headers[CSRF_HEADER]).toBe("explicit");
    });

    it("omits the header when no token is available", async () => {
      useSessionStore.setState({ sessionDetails: {} });
      vi.spyOn(Cookies, "get").mockReturnValue(undefined);
      const result = await runRequestInterceptors(withInterceptor(), {
        method: "post",
        url: "/api/v1/items/",
      });
      expect(CSRF_HEADER in result.headers).toBe(false);
    });

    it("reads the token per request, not at attach time", async () => {
      const instance = withInterceptor();
      useSessionStore.setState({ sessionDetails: { csrfToken: "rotated" } });
      const result = await runRequestInterceptors(instance, {
        method: "post",
        url: "/api/v1/items/",
      });
      expect(result.headers[CSRF_HEADER]).toBe("rotated");
    });
  });

  describe("getCsrfHeaders", () => {
    it("returns the header object", () => {
      expect(getCsrfHeaders()).toEqual({ [CSRF_HEADER]: "store-tok" });
    });

    it("returns an empty object without a token", () => {
      useSessionStore.setState({ sessionDetails: {} });
      vi.spyOn(Cookies, "get").mockReturnValue(undefined);
      expect(getCsrfHeaders()).toEqual({});
    });
  });
});
