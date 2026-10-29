import type { Ref, RefCallback } from "react";

type Cleanup = () => void;

function setRef<T>(ref: Ref<T> | undefined, node: T | null): Cleanup | null {
  if (typeof ref === "function") {
    const cleanup = ref(node);
    return typeof cleanup === "function" ? cleanup : null;
  }
  if (ref) {
    ref.current = node;
  }
  return null;
}

/*
 * One ref callback that feeds every given ref, for a component that needs its
 * node and also forwards the caller's ref. It returns a cleanup, so React 19
 * calls that instead of the callback with null: a ref that returned its own
 * cleanup gets it run, every other ref is set to null.
 */
export function composeRefs<T>(
  ...refs: readonly (Ref<T> | undefined)[]
): RefCallback<T> {
  return (node) => {
    const cleanups = refs.map((ref) => setRef(ref, node));
    return () => {
      refs.forEach((ref, index) => {
        const cleanup = cleanups[index];
        if (cleanup) {
          cleanup();
        } else {
          setRef(ref, null);
        }
      });
    };
  };
}
