import { createRef } from "react";
import { expect, it, vi } from "vitest";
import { composeRefs } from "./compose-refs";

it("sets object refs and calls callback refs, skipping missing ones", () => {
  const objectRef = createRef<string>();
  const callbackRef = vi.fn();
  const ref = composeRefs<string>(objectRef, undefined, callbackRef, null);
  ref("node");
  expect(objectRef.current).toBe("node");
  expect(callbackRef).toHaveBeenCalledWith("node");
});

it("runs a ref's own cleanup on detach, and nulls the refs that have none", () => {
  const objectRef = createRef<string>();
  const plainCallback = vi.fn();
  const ownCleanup = vi.fn();
  const cleanupRef = vi.fn(() => ownCleanup);
  const detach = composeRefs<string>(
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
