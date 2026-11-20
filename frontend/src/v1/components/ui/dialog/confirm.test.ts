import { afterEach, expect, it, vi } from "vitest";
import {
  confirm,
  currentConfirm,
  settleConfirm,
  subscribeConfirm,
} from "./confirm";

let unsubscribe: (() => void) | null = null;

function mountHost(): ReturnType<typeof vi.fn> {
  const onChange = vi.fn();
  unsubscribe = subscribeConfirm(onChange);
  return onChange;
}

afterEach(() => {
  unsubscribe?.();
  unsubscribe = null;
});

const DELETE = {
  tone: "destructive",
  title: "Delete “Invoice API”?",
  description: "The endpoint stops responding immediately.",
  consequence: "This cannot be undone.",
  confirmLabel: "Delete deployment",
} as const;

it("resolves false and warns when no host is mounted", async () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  await expect(confirm(DELETE)).resolves.toBe(false);
  expect(warn).toHaveBeenCalledWith(
    "[v1 confirm] no ConfirmHost mounted: %s",
    DELETE.title,
  );
  expect(currentConfirm()).toBeNull();
});

it("shows one request at a time and answers them in order", async () => {
  const onChange = mountHost();
  const first = confirm(DELETE);
  const second = confirm({
    title: "Regenerate the key?",
    description: "The current key stops working.",
    confirmLabel: "Regenerate key",
  });
  expect(onChange).toHaveBeenCalledTimes(2);

  const head = currentConfirm();
  expect(head?.options.title).toBe(DELETE.title);
  settleConfirm(head?.id ?? -1, true);
  await expect(first).resolves.toBe(true);

  const next = currentConfirm();
  expect(next?.options.title).toBe("Regenerate the key?");
  settleConfirm(next?.id ?? -1, false);
  await expect(second).resolves.toBe(false);
  expect(currentConfirm()).toBeNull();
});

it("resolves a blocked request false even when settled true", async () => {
  mountHost();
  const answer = confirm({
    tone: "blocked",
    title: "Invoice Vendor Lookup cannot be deleted",
    reason: "Unlink it from the project first.",
  });
  settleConfirm(currentConfirm()?.id ?? -1, true);
  await expect(answer).resolves.toBe(false);
});

it("ignores an answer for a request that is not on screen", () => {
  mountHost();
  void confirm(DELETE);
  const head = currentConfirm();
  settleConfirm((head?.id ?? 0) + 1, true);
  expect(currentConfirm()).toBe(head);
});

it("answers every waiting request false when the host unmounts", async () => {
  mountHost();
  const first = confirm(DELETE);
  const second = confirm(DELETE);
  unsubscribe?.();
  unsubscribe = null;
  await expect(first).resolves.toBe(false);
  await expect(second).resolves.toBe(false);
  expect(currentConfirm()).toBeNull();
});

it("leaves the queue alone when a replaced host unsubscribes", () => {
  const stale = subscribeConfirm(vi.fn());
  mountHost();
  void confirm(DELETE);
  stale();
  expect(currentConfirm()?.options.title).toBe(DELETE.title);
});
