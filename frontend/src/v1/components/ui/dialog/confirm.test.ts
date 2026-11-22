import { afterEach, expect, it, vi } from "vitest";
import {
  type ConfirmOptions,
  confirm,
  currentConfirm,
  setConfirmRunning,
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

it("keeps a request asked before the host subscribes in the same task", async () => {
  const answer = confirm(DELETE);
  mountHost();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(currentConfirm()?.options.title).toBe(DELETE.title);
  settleConfirm(currentConfirm()?.id ?? -1, true);
  await expect(answer).resolves.toBe(true);
});

it("refuses a request while the one on screen runs its action, and logs it", async () => {
  mountHost();
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  void confirm(DELETE);
  const id = currentConfirm()?.id ?? -1;
  setConfirmRunning(id, true);
  await expect(confirm(DELETE)).resolves.toBe(false);
  expect(error).toHaveBeenCalledOnce();
  setConfirmRunning(id + 1, false);
  await expect(confirm(DELETE)).resolves.toBe(false);
  setConfirmRunning(id, false);
  void confirm(DELETE);
  settleConfirm(id, true);
  expect(currentConfirm()).not.toBeNull();
});

it("stops refusing once the host that ran the action unmounts", async () => {
  mountHost();
  void confirm(DELETE);
  setConfirmRunning(currentConfirm()?.id ?? -1, true);
  unsubscribe?.();
  mountHost();
  void confirm(DELETE);
  expect(currentConfirm()?.options.title).toBe(DELETE.title);
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
  expect(onChange).toHaveBeenCalledTimes(3);

  const next = currentConfirm();
  expect(next?.options.title).toBe("Regenerate the key?");
  settleConfirm(next?.id ?? -1, false);
  await expect(second).resolves.toBe(false);
  expect(onChange).toHaveBeenCalledTimes(4);
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

it("ignores a late answer for a request already answered", async () => {
  mountHost();
  const first = confirm(DELETE);
  const second = confirm(DELETE);
  const id = currentConfirm()?.id ?? -1;
  settleConfirm(id, true);
  settleConfirm(id, true);
  await expect(first).resolves.toBe(true);
  expect(currentConfirm()?.id).not.toBe(id);
  const pending = await Promise.race([second, Promise.resolve("pending")]);
  expect(pending).toBe("pending");
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
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  await expect(confirm(DELETE)).resolves.toBe(false);
});

it("leaves the queue alone when a replaced host unsubscribes", () => {
  const stale = subscribeConfirm(vi.fn());
  mountHost();
  void confirm(DELETE);
  stale();
  expect(currentConfirm()?.options.title).toBe(DELETE.title);
  void confirm(DELETE);
  settleConfirm(currentConfirm()?.id ?? -1, true);
  expect(currentConfirm()?.options.title).toBe(DELETE.title);
});

// Type-level guard, never run: each tone's own text is required and present.
export function _confirmTypesHoldTheirTone(warning?: string): ConfirmOptions[] {
  const base = {
    title: "Delete?",
    confirmLabel: "Delete",
    description: "Gone.",
  };
  const destructive = { ...base, tone: "destructive" } as const;
  return [
    base,
    // @ts-expect-error a consequence needs the destructive tone
    { ...base, consequence: "Cannot be undone." },
    // @ts-expect-error a reason needs the blocked tone
    { ...base, reason: "Linked to a project." },
    // @ts-expect-error a destructive consequence cannot be missing
    { ...destructive, consequence: warning },
  ];
}
