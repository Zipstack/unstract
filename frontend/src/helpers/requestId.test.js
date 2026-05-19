import axios from "axios";
import { describe, expect, it } from "vitest";

import {
  attachRequestIdInterceptor,
  getRequestIdFromError,
  REQUEST_ID_HEADER,
} from "./requestId";

const UUID_V4_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const runRequestInterceptors = async (instance, config = {}) => {
  let current = { ...config, headers: { ...(config.headers || {}) } };
  for (const handler of instance.interceptors.request.handlers) {
    if (handler && handler.fulfilled) {
      current = await handler.fulfilled(current);
    }
  }
  return current;
};

describe("attachRequestIdInterceptor", () => {
  it("injects a v4 UUID when the header is absent", async () => {
    const instance = axios.create();
    attachRequestIdInterceptor(instance);

    const result = await runRequestInterceptors(instance);

    expect(result.headers[REQUEST_ID_HEADER]).toMatch(UUID_V4_REGEX);
  });

  it("does NOT overwrite a caller-supplied X-Request-ID", async () => {
    const instance = axios.create();
    attachRequestIdInterceptor(instance);

    const supplied = "caller-provided-id";
    const result = await runRequestInterceptors(instance, {
      headers: { [REQUEST_ID_HEADER]: supplied },
    });

    expect(result.headers[REQUEST_ID_HEADER]).toBe(supplied);
  });

  it("generates a distinct ID per request", async () => {
    const instance = axios.create();
    attachRequestIdInterceptor(instance);

    const first = await runRequestInterceptors(instance);
    const second = await runRequestInterceptors(instance);

    expect(first.headers[REQUEST_ID_HEADER]).not.toBe(
      second.headers[REQUEST_ID_HEADER],
    );
  });

  it("creates a headers object when one is missing on the config", async () => {
    const instance = axios.create();
    attachRequestIdInterceptor(instance);

    let current = {};
    for (const handler of instance.interceptors.request.handlers) {
      if (handler && handler.fulfilled) {
        current = await handler.fulfilled(current);
      }
    }

    expect(current.headers[REQUEST_ID_HEADER]).toMatch(UUID_V4_REGEX);
  });
});

describe("getRequestIdFromError", () => {
  it("reads the lowercased response header", () => {
    const err = {
      response: { headers: { "x-request-id": "from-response" } },
      config: { headers: { [REQUEST_ID_HEADER]: "from-config" } },
    };

    expect(getRequestIdFromError(err)).toBe("from-response");
  });

  it("falls back to the request config header when no response header exists", () => {
    const err = {
      config: { headers: { [REQUEST_ID_HEADER]: "from-config" } },
    };

    expect(getRequestIdFromError(err)).toBe("from-config");
  });

  it("returns undefined for null/empty error inputs without throwing", () => {
    expect(getRequestIdFromError(null)).toBeUndefined();
    expect(getRequestIdFromError(undefined)).toBeUndefined();
    expect(getRequestIdFromError({})).toBeUndefined();
  });
});
