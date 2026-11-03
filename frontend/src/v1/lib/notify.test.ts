import { afterEach, expect, it, vi } from "vitest";
import {
  dismissNotification,
  type Notifier,
  notify,
  setNotifier,
  toast,
} from "./notify";

afterEach(() => {
  vi.restoreAllMocks();
});

function fakeNotifier(): Notifier & { shown: unknown[]; dismissed: string[] } {
  const shown: unknown[] = [];
  const dismissed: string[] = [];
  return {
    shown,
    dismissed,
    show: (input) => {
      shown.push(input);
      return "id-1";
    },
    dismiss: (id) => {
      dismissed.push(id);
    },
  };
}

it("sends notifications to the registered notifier and returns its id", () => {
  const fake = fakeNotifier();
  const unregister = setNotifier(fake);
  expect(notify({ kind: "success", title: "Saved" })).toBe("id-1");
  dismissNotification("id-1");
  unregister();
  expect(fake.shown).toEqual([{ kind: "success", title: "Saved" }]);
  expect(fake.dismissed).toEqual(["id-1"]);
});

it("logs with the request id when no notifier is mounted, so nothing is silent", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  expect(
    notify({
      kind: "error",
      title: "Could not save",
      description: "Server error",
      requestId: "req-42",
    }),
  ).toBeUndefined();
  notify({ kind: "warning", title: "Slow" });
  expect(error).toHaveBeenCalledWith(
    "[v1 notify] Could not save: Server error (request req-42)",
  );
  expect(warn).toHaveBeenCalledWith("[v1 notify] Slow");
});

it("unregistering an older notifier leaves the newer one in place", () => {
  const first = fakeNotifier();
  const second = fakeNotifier();
  const unregisterFirst = setNotifier(first);
  const unregisterSecond = setNotifier(second);
  unregisterFirst();
  notify({ kind: "info", title: "Hi" });
  unregisterSecond();
  expect(first.shown).toEqual([]);
  expect(second.shown).toHaveLength(1);
});

it("has one shorthand per kind", () => {
  const fake = fakeNotifier();
  const unregister = setNotifier(fake);
  toast.success("a");
  toast.error("b", { requestId: "r" });
  toast.warning("c");
  toast.info("d", { persistent: true });
  unregister();
  expect(fake.shown).toEqual([
    { kind: "success", title: "a" },
    { kind: "error", title: "b", requestId: "r" },
    { kind: "warning", title: "c" },
    { kind: "info", title: "d", persistent: true },
  ]);
});
