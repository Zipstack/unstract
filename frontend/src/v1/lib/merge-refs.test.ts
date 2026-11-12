import { createRef } from "react";
import { expect, it, vi } from "vitest";
import { mergeRefs } from "./merge-refs";

it("sets object refs and calls callback refs, skipping missing ones", () => {
  const objectRef = createRef<string>();
  const callbackRef = vi.fn();
  const ref = mergeRefs<string>(objectRef, undefined, callbackRef, null);
  ref("node");
  expect(objectRef.current).toBe("node");
  expect(callbackRef).toHaveBeenCalledWith("node");
});

it("runs a ref's own cleanup on detach, and nulls the refs that have none", () => {
  const objectRef = createRef<string>();
  const plainCallback = vi.fn();
  const ownCleanup = vi.fn();
  const cleanupRef = vi.fn(() => ownCleanup);
  const detach = mergeRefs<string>(
    objectRef,
    plainCallback,
    cleanupRef,
  )("node");
  expect(typeof detach).toBe("function");

  (detach as () => void)();
  expect(ownCleanup).toHaveBeenCalledOnce();
  expect(cleanupRef).not.toHaveBeenCalledWith(null);
  expect(plainCallback).toHaveBeenLastCalledWith(null);
  expect(objectRef.current).toBeNull();
});
