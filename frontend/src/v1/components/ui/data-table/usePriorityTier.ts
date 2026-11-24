import { useSyncExternalStore } from "react";
import { PRIORITY_MIN_WIDTH, priorityForWidth } from "./columns";
import type { DataTableColumnPriority } from "./types";

/*
 * The highest column priority the screen has room for. Media queries, not the
 * table's own width: the dev spec's breakpoints are screen widths, and a
 * query only fires when one is crossed, so resizing does not re-render the
 * table on every pixel.
 */

const BREAKPOINTS = [
  PRIORITY_MIN_WIDTH[2],
  PRIORITY_MIN_WIDTH[3],
  PRIORITY_MIN_WIDTH[4],
];

function queries(): MediaQueryList[] {
  if (typeof window === "undefined" || !window.matchMedia) {
    return [];
  }
  return BREAKPOINTS.map((width) =>
    window.matchMedia(`(min-width: ${width}px)`),
  );
}

function subscribe(onChange: () => void): () => void {
  const lists = queries();
  for (const list of lists) {
    list.addEventListener("change", onChange);
  }
  return () => {
    for (const list of lists) {
      list.removeEventListener("change", onChange);
    }
  };
}

function snapshot(): DataTableColumnPriority {
  const lists = queries();
  if (lists.length === 0) {
    return 4;
  }
  const widest = BREAKPOINTS.filter((_, i) => lists[i].matches).at(-1) ?? 0;
  return priorityForWidth(widest);
}

/** Every column shows where the screen cannot be measured (server render). */
const serverSnapshot = (): DataTableColumnPriority => 4;

export function usePriorityTier(): DataTableColumnPriority {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
