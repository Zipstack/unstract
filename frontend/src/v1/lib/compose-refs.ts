import type { Ref, RefCallback } from "react";

/** One ref callback that feeds every given ref, for a component that needs its node and also forwards the caller's ref. */
export function composeRefs<T>(
  ...refs: readonly (Ref<T> | undefined)[]
): RefCallback<T> {
  return (node) => {
    for (const ref of refs) {
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    }
  };
}
