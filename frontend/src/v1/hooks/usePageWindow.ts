import { PAGE_OVERSCAN, pageWindow } from "@v1/lib/pdf/windowing";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/** The attribute each observed page carries, holding its 0-based index. */
const PAGE_INDEX_ATTRIBUTE = "data-page-index";

export interface PageWindow {
  /** Ref for the scrolling container the pages are measured against. */
  scrollRef: (element: HTMLElement | null) => void;
  /** Ref for each page element; it must carry `data-page-index`. */
  observePage: (element: HTMLElement | null) => (() => void) | undefined;
  /** 0-based pages currently in view. */
  visible: ReadonlySet<number>;
  /** 0-based pages that should hold a canvas: the visible ones ± overscan. */
  rendered: ReadonlySet<number>;
}

function sameMembers(a: ReadonlySet<number>, b: ReadonlySet<number>): boolean {
  if (a.size !== b.size) {
    return false;
  }
  for (const value of a) {
    if (!b.has(value)) {
      return false;
    }
  }
  return true;
}

function pageIndexOf(element: Element): number {
  return Number(element.getAttribute(PAGE_INDEX_ATTRIBUTE));
}

/**
 * Tracks which pages are in view with one IntersectionObserver on the scroll
 * container, and derives the pages to render from them.
 */
export function usePageWindow(
  pageCount: number,
  overscan: number = PAGE_OVERSCAN,
): PageWindow {
  const [root, setRoot] = useState<HTMLElement | null>(null);
  const [visible, setVisible] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const observerRef = useRef<IntersectionObserver | null>(null);
  const pages = useRef(new Set<HTMLElement>());

  useEffect(() => {
    if (root === null) {
      return;
    }
    const inView = new Set<number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = pageIndexOf(entry.target);
          if (entry.isIntersecting) {
            inView.add(index);
          } else {
            inView.delete(index);
          }
        }
        const next = new Set(inView);
        setVisible((previous) =>
          sameMembers(previous, next) ? previous : next,
        );
      },
      { root },
    );
    observerRef.current = observer;
    for (const page of pages.current) {
      observer.observe(page);
    }
    return () => {
      observer.disconnect();
      observerRef.current = null;
    };
  }, [root]);

  const observePage = useCallback((element: HTMLElement | null) => {
    if (element === null) {
      return undefined;
    }
    pages.current.add(element);
    observerRef.current?.observe(element);
    return () => {
      pages.current.delete(element);
      observerRef.current?.unobserve(element);
    };
  }, []);

  const rendered = useMemo(
    () => pageWindow(visible, pageCount, overscan),
    [visible, pageCount, overscan],
  );

  return { scrollRef: setRoot, observePage, visible, rendered };
}
