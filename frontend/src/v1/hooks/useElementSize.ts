import { useCallback, useEffect, useState } from "react";

export interface ElementSize {
  width: number;
  height: number;
}

/**
 * An element's content-box size, kept current with a ResizeObserver. Returns a
 * ref for the element and its size, null until it has been measured.
 */
export function useElementSize<T extends HTMLElement>(): [
  (element: T | null) => void,
  ElementSize | null,
] {
  const [element, setElement] = useState<T | null>(null);
  const [size, setSize] = useState<ElementSize | null>(null);

  useEffect(() => {
    if (element === null) {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) {
        return;
      }
      const { width, height } = entry.contentRect;
      setSize((previous) =>
        previous?.width === width && previous.height === height
          ? previous
          : { width, height },
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  const ref = useCallback((next: T | null) => setElement(next), []);
  return [ref, size];
}
