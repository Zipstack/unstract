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
