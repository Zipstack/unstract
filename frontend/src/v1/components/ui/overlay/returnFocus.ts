import { useCallback, useLayoutEffect, useRef } from "react";

// Focus return for overlays built on a Radix Dialog: back to whatever opened them.

const LAYER = "[role=menu], [role=dialog]";

// The page control (outside any menu or dialog) that last took focus; cleared when it loses focus to nothing.
let pageFocus: HTMLElement | null = null;

function trackPageFocus(doc: Document): void {
  doc.addEventListener("focusin", (event) => {
    const { target } = event;
    if (target instanceof HTMLElement && !target.closest(LAYER)) {
      pageFocus = target;
    }
  });
  doc.addEventListener("focusout", (event) => {
    if (event.target === pageFocus && event.relatedTarget === null) {
      pageFocus = null;
    }
  });
}

if (typeof document !== "undefined") {
  trackPageFocus(document);
}

/** The control that opened the menu or popover `element` sits in. */
function controllerOf(element: HTMLElement): HTMLElement | null {
  const layer = element.closest<HTMLElement>(LAYER);
  if (!layer) {
    return null;
  }
  const doc = element.ownerDocument;
  // A Radix menu is labelled by its trigger; a popover's trigger controls it.
  const labelledBy = layer.getAttribute("aria-labelledby");
  if (layer.getAttribute("role") === "menu" && labelledBy) {
    return doc.getElementById(labelledBy);
  }
  const controls = doc.querySelectorAll<HTMLElement>("[aria-controls]");
  return (
    [...controls].find((c) => c.getAttribute("aria-controls") === layer.id) ??
    null
  );
}

/** The focused element, each control that opened the layer it sits in, then the last focused page control. */
function openersOf(doc: Document): HTMLElement[] {
  const chain: HTMLElement[] = [];
  let current = doc.activeElement;
  while (
    current instanceof HTMLElement &&
    current !== doc.body &&
    !chain.includes(current)
  ) {
    chain.push(current);
    current = controllerOf(current);
  }
  if (pageFocus && !chain.includes(pageFocus)) {
    chain.push(pageFocus);
  }
  return chain;
}

/** Takes the controlled `open`; returns an `onCloseAutoFocus` that refocuses the first opener still on the page. */
export function useReturnFocus(open: boolean): (event: Event) => void {
  const openers = useRef<HTMLElement[]>([]);
  const isOpen = useRef(open);
  // A layout effect runs before a menu or popover that opened the overlay unmounts.
  useLayoutEffect(() => {
    isOpen.current = open;
    const next = open ? openersOf(document) : [];
    // Reopened with focus on the page (chained confirms): keep the first opener.
    if (next.length > 0) {
      openers.current = next;
    }
    // Unmounted while open: the close that follows is real.
    return () => {
      isOpen.current = false;
    };
  }, [open]);
  return useCallback((event: Event) => {
    // A late close from before a reopen: the reopened overlay keeps focus.
    if (isOpen.current) {
      event.preventDefault();
      return;
    }
    const target = openers.current.find((element) => element.isConnected);
    openers.current = [];
    if (target) {
      event.preventDefault();
      target.focus();
    }
  }, []);
}
