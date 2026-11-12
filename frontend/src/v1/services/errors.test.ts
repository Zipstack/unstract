import { CancelledError } from "@tanstack/react-query";
import { HttpResponse, http as mock, mockApi } from "@v1/test";
import { CanceledError } from "axios";
import type { JsonBodyType } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onSessionExpired } from "./context";
import {
  ApiError,
  isCancelled,
  isTransient,
  mapFieldErrors,
  REQUEST_ID_HEADER,
  toApiError,
} from "./errors";
import { createHttpClient } from "./http";

const URL = "/api/v1/thing/";
const SENT_ID = "sent-1";

/* What the client rejects with when the backend answers `response`. */
async function failureFor(response: Response | (() => Response)) {
  mockApi(
    mock.all(URL, typeof response === "function" ? response : () => response),
  );
  const headers = { [REQUEST_ID_HEADER]: SENT_ID };
  const error = await createHttpClient()
    .post(URL, {}, { headers })
    .catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

const json = (body: JsonBodyType, status: number, headers?: HeadersInit) =>
  HttpResponse.json(body, { status, headers });

let cleanup: () => void;
beforeEach(() => {
  // A 401 would otherwise send the test's window to the logout URL.
  cleanup = onSessionExpired(vi.fn());
});
afterEach(() => cleanup());

describe("each kind, from the backend's own error bodies", () => {
  it("validation: field and non-field errors, all in the message", async () => {
    const error = await failureFor(
      json(
        {
          type: "validation_error",
          errors: [
            {
              code: "required",
              detail: "This field is required.",
              attr: "adapter_name",
            },
            {
              code: "blank",
              detail: "May not be blank.",
              attr: "adapter_name",
            },
            {
              code: "invalid",
              detail: "Name already taken.",
              attr: "non_field_errors",
            },
          ],
        },
        400,
      ),
    );
    expect(error).toMatchObject({
      kind: "validation",
      status: 400,
      fieldErrors: {
        adapter_name: ["This field is required.", "May not be blank."],
      },
      formErrors: ["Name already taken."],
    });
    expect(error.message).toBe(
      "adapter_name: This field is required. adapter_name: May not be blank. Name already taken.",
    );
  });

  it("subscription: the plugin's 402 body", async () => {
    const error = await failureFor(
      json(
        {
          type: "subscription_error",
          errors: "Trial period expired. Please contact sales/admin.",
        },
        402,
      ),
    );
    expect(error).toMatchObject({
      kind: "subscription",
      message: "Trial period expired. Please contact sales/admin.",
    });
  });

  it("subscription: a 400 whose error code is subscription_error", async () => {
    const error = await failureFor(
      json(
        {
          type: "client_error",
          errors: [
            {
              code: "subscription_error",
              detail: "Selected organization is not active.",
              attr: null,
            },
          ],
        },
        400,
      ),
    );
    expect(error).toMatchObject({
      kind: "subscription",
      message: "Selected organization is not active.",
    });
  });

  it("unauthenticated: the auth middleware's 401", async () => {
    const error = await failureFor(json({ message: "Unauthorized" }, 401));
    expect(error).toMatchObject({ kind: "unauthenticated", status: 401 });
  });

  it.each([
    [
      "a provider rejecting its key",
      { error: "Invalid API key.", type: "sdk_error" },
      "Invalid API key.",
    ],
    [
      "a connector's failed OAuth refresh",
      {
        type: "client_error",
        errors: [{ code: "error", detail: "OAuth failed.", attr: null }],
      },
      "OAuth failed.",
    ],
  ])("client, not session expiry: a typed 401 from %s", async (_, body, message) => {
    const expired = vi.fn();
    const restore = onSessionExpired(expired);
    const error = await failureFor(json(body, 401));
    restore();
    expect(error).toMatchObject({ kind: "client", status: 401, message });
    expect(expired).not.toHaveBeenCalled();
  });

  it("forbidden: the auth middleware's 403", async () => {
    const error = await failureFor(
      json({ message: "Organization access denied" }, 403),
    );
    expect(error).toMatchObject({
      kind: "forbidden",
      message: "Organization access denied",
    });
  });

  it("not found: the resource-named 404", async () => {
    const error = await failureFor(
      json(
        {
          type: "client_error",
          errors: [
            { code: "not_found", detail: "Adapter not found.", attr: null },
          ],
        },
        404,
      ),
    );
    expect(error).toMatchObject({
      kind: "not_found",
      message: "Adapter not found.",
    });
  });

  it("client: any other 4xx", async () => {
    const error = await failureFor(json({ detail: "Already exists." }, 409));
    expect(error).toMatchObject({ kind: "client", message: "Already exists." });
    expect(error.fieldErrors).toEqual({});
  });

  it("server: a non-JSON 502 gets the default message and the echoed request id", async () => {
    const error = await failureFor(
      new HttpResponse("<html>Bad Gateway</html>", {
        status: 502,
        headers: { "Content-Type": "text/html", [REQUEST_ID_HEADER]: "srv-9" },
      }),
    );
    expect(error).toMatchObject({
      kind: "server",
      status: 502,
      message: "Something went wrong on our side. Try again.",
      requestId: "srv-9",
    });
  });

  it("server: the SDK's error text", async () => {
    const error = await failureFor(
      json({ error: "LLM call failed", type: "sdk_error" }, 500),
    );
    expect(error).toMatchObject({ kind: "server", message: "LLM call failed" });
  });

  it("network: no response, with the request id that was sent", async () => {
    const error = await failureFor(() => HttpResponse.error());
    expect(error).toMatchObject({
      kind: "network",
      status: undefined,
      requestId: SENT_ID,
    });
  });

  it("unknown: anything that is not an HTTP failure", () => {
    const cause = new TypeError("x is undefined");
    expect(toApiError(cause)).toMatchObject({
      kind: "unknown",
      message: "Something went wrong.",
      cause,
    });
  });

  it("unknown, not network: a cancelled request", () => {
    for (const cause of [new CanceledError(), new CancelledError()]) {
      expect(toApiError(cause)).toMatchObject({
        kind: "unknown",
        message: "The request was cancelled.",
        cause,
      });
    }
  });

  it("returns an ApiError as it is", () => {
    const error = new ApiError({ kind: "client", message: "m" });
    expect(toApiError(error)).toBe(error);
  });
});

describe("isCancelled and isTransient", () => {
  it("recognises axios and TanStack cancellations", () => {
    expect(isCancelled(new CanceledError())).toBe(true);
    expect(isCancelled(new CancelledError())).toBe(true);
    expect(isCancelled(new ApiError({ kind: "network", message: "m" }))).toBe(
      false,
    );
  });

  it("calls only network and gateway failures transient", () => {
    const failure = (kind: ApiError["kind"], status?: number) =>
      new ApiError({ kind, message: "m", status });
    expect(isTransient(failure("network"))).toBe(true);
    expect(isTransient(failure("server", 503))).toBe(true);
    expect(isTransient(failure("server", 500))).toBe(false);
    expect(isTransient(failure("validation", 400))).toBe(false);
    expect(isTransient(new CanceledError())).toBe(false);
  });
});

describe("mapFieldErrors", () => {
  const validation = new ApiError({
    kind: "validation",
    message: "all",
    fieldErrors: { adapter_name: ["Required."], metadata: ["Bad JSON."] },
    formErrors: ["Name already taken."],
  });

  it("maps shown fields and moves the rest into the form-level message", () => {
    expect(mapFieldErrors(validation, ["adapter_name", "description"])).toEqual(
      {
        fields: { adapter_name: "Required." },
        form: "Name already taken. metadata: Bad JSON.",
      },
    );
  });

  it("leaves no form-level message when every error has a field", () => {
    const fieldsOnly = new ApiError({
      kind: "validation",
      message: "m",
      fieldErrors: { adapter_name: ["Required."] },
    });
    expect(mapFieldErrors(fieldsOnly, ["adapter_name"])).toEqual({
      fields: { adapter_name: "Required." },
      form: undefined,
    });
  });

  it.each([
    ["an idle mutation (null)", null],
    ["no error (undefined)", undefined],
    ["a cancelled request", new CanceledError()],
  ])("shows nothing for %s", (_, error) => {
    expect(mapFieldErrors(error, ["adapter_name"])).toEqual({
      fields: {},
      form: undefined,
    });
  });

  it("puts any other failure in the form-level message", () => {
    expect(mapFieldErrors(new TypeError("x"), ["adapter_name"])).toEqual({
      fields: {},
      form: "Something went wrong.",
    });
  });
});
