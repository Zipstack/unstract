import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import { CanceledError } from "axios";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { reportApiError } from "./report";

let shown: NotifyInput[];
let unregister: () => void;

beforeEach(() => {
  shown = [];
  unregister = setNotifier({
    show: (input) => {
      shown.push(input);
      return "toast-1";
    },
    dismiss: () => undefined,
  });
});
afterEach(() => unregister());

const failure = (kind: ApiError["kind"]) =>
  new ApiError({ kind, message: `${kind} message`, requestId: "req-1" });

it("shows a failure as an error toast with its request id", () => {
  reportApiError(failure("server"), { id: "q1" });
  expect(shown).toEqual([
    {
      kind: "error",
      title: "server message",
      requestId: "req-1",
      persistent: false,
      id: "q1",
    },
  ]);
});

it("keeps a subscription failure until it is dismissed", () => {
  reportApiError(failure("subscription"));
  expect(shown[0]).toMatchObject({ persistent: true });
});

it("only logs, with the request id, when the caller shows the error", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  reportApiError(failure("validation"), { notify: false });
  expect(shown).toEqual([]);
  expect(warn).toHaveBeenCalledWith(
    "[v1 api] %s (request %s)",
    "validation message",
    "req-1",
  );
});

it("reports nothing for a cancellation or an expired session", () => {
  reportApiError(new CanceledError());
  reportApiError(failure("unauthenticated"));
  expect(shown).toEqual([]);
});

it("logs the cause of an unexpected failure and still shows it", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const cause = new TypeError("boom");
  reportApiError(cause);
  expect(error).toHaveBeenCalledWith("[v1 api] unexpected failure", cause);
  expect(shown).toEqual([
    expect.objectContaining({ title: "Something went wrong." }),
  ]);
});
