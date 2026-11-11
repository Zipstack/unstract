import { useDevicePixelRatio } from "@v1/hooks/useDevicePixelRatio";
import { usePageWindow } from "@v1/hooks/usePageWindow";
import { cn } from "@v1/lib/cn";
import {
  type Highlight,
  highlightsByPage,
  NO_HIGHLIGHTS,
} from "@v1/lib/pdf/highlights";
import type { PageSize } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  type KeyboardEvent,
  type ReactNode,
  type Ref,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { PdfPage } from "./PdfPage";

export interface PdfPageListHandle {
  /** Scrolls a 0-based page to the top of the viewer. */
  scrollToPage: (index: number) => void;
  /** Centres a highlight in the viewer. False when no highlight has that id. */
  scrollToHighlight: (id: string) => boolean;
}

export interface PdfPageListProps {
  document: PDFDocumentProxy;
  pageSizes: readonly PageSize[];
  /** 1 is 100%. */
  zoom: number;
  /** Highlights on any page, from the normalisers in `@v1/lib/pdf/highlights`. */
  highlights?: readonly Highlight[];
  activeHighlightId?: string | null;
  /** Keep it stable (useCallback): a new function re-renders every page. */
  onHighlightClick?: (highlight: Highlight) => void;
  /** Called with the 0-based page showing most of itself. */
  onCurrentPageChange?: (index: number) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  /**
   * Drawn over a page, above its highlights; receives the 0-based page index.
   * Keep it stable (useCallback): a new function re-renders every page.
   */
  renderPageOverlay?: (index: number) => ReactNode;
  className?: string;
  ref?: Ref<PdfPageListHandle>;
}

/** Where the reader is, kept across a zoom change: a page and a share of it. */
interface Anchor {
  index: number;
  fraction: number;
  /**
   * Where across that page the middle of the view is, as a share of the
   * page's width. It falls outside 0 to 1 when the middle of the view is
   * beside a narrower page, so it must not be clamped.
   */
  across: number;
}

function pageElement(root: HTMLElement, index: number): HTMLElement | null {
  return root.querySelector<HTMLElement>(`[data-page-index="${index}"]`);
}

/** A page's top in scroll coordinates, so that page 0 sits at 0. */
function pageTop(root: HTMLElement, page: HTMLElement): number {
  const first = pageElement(root, 0);
  return page.offsetTop - (first?.offsetTop ?? 0);
}

/** The page elements in index order, read with one query per measurement. */
function pageElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-page-index]"));
}

/**
 * The first index whose `edge` is past `y`, or the page count when none is,
 * found by halving the range.
 */
function firstPast(
  pages: readonly HTMLElement[],
  y: number,
  edge: (page: HTMLElement) => number,
): number {
  let low = 0;
  let high = pages.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    const page = pages[middle];
    if (page && edge(page) > y) {
      high = middle;
    } else {
      low = middle + 1;
    }
  }
  return low;
}

/**
 * The page showing the largest share of itself in view (a page taller than
 * the view counts the view as whole); the lower index wins a tie, and
 * the last page wins once the end is reached, where a short last page could
 * otherwise never show the most. Read from the layout, so it is exact for
 * pages of any height and right straight after a jump, unlike intersection
 * ratios, which only arrive at thresholds and a frame later.
 */
function mostVisiblePage(
  root: HTMLElement,
  pages: readonly HTMLElement[],
): number {
  const last = pages.length - 1;
  const scrollable = root.scrollHeight > root.clientHeight;
  if (
    scrollable &&
    root.scrollTop >= root.scrollHeight - root.clientHeight - 1
  ) {
    return last;
  }
  // In the content's own coordinates, where the padding sits above page 0.
  const top = root.scrollTop;
  const bottom = top + root.clientHeight;
  let best = Math.min(
    last,
    firstPast(pages, top, (page) => page.offsetTop + page.offsetHeight),
  );
  let bestShown = Number.NEGATIVE_INFINITY;
  for (let index = best; index <= last; index++) {
    const page = pages[index];
    if (!page || page.offsetTop >= bottom) {
      break;
    }
    const shown =
      (Math.min(page.offsetTop + page.offsetHeight, bottom) -
        Math.max(page.offsetTop, top)) /
      // A share of what the page could show: of itself, or of the view when
      // it is taller than the view. Raw pixels would let part of a tall page
      // beat a short page shown whole.
      Math.max(1, Math.min(page.offsetHeight, root.clientHeight));
    if (shown > bestShown) {
      best = index;
      bestShown = shown;
    }
  }
  return best;
}

/**
 * Every page of a document in one scrolling column. All pages are laid out at
 * their real size from the start, so the scrollbar is right and scrolling to
 * any page or highlight lands exactly without waiting for a render, but only
 * the pages in view (± 2) hold a canvas.
 */
export function PdfPageList({
  document,
  pageSizes,
  zoom,
  highlights = NO_HIGHLIGHTS,
  activeHighlightId,
  onHighlightClick,
  onCurrentPageChange,
  onKeyDown,
  renderPageOverlay,
  className,
  ref,
}: PdfPageListProps) {
  const pageCount = pageSizes.length;
  const { scrollRef, observePage, rendered } = usePageWindow(pageCount);
  const byPage = useMemo(() => highlightsByPage(highlights), [highlights]);
  const rootRef = useRef<HTMLElement | null>(null);
  const anchorRef = useRef<Anchor>({
    index: 0,
    fraction: 0,
    across: 0.5,
  });
  // The last page jumped to and where the jump landed. While the view stays
  // there, that page is current, even when the browser clamped the jump at
  // the end and another page shows more: otherwise Previous could never
  // leave the last page when the last few pages fit together.
  const jumpRef = useRef<{ index: number; scrollTop: number } | null>(null);
  const [current, setCurrent] = useState(0);
  // The page elements, read once: the list is keyed per document and its
  // pages never remount, so scrolling never has to query the DOM again.
  const pagesRef = useRef<HTMLElement[]>([]);

  const setRoot = useCallback(
    (element: HTMLElement | null) => {
      rootRef.current = element;
      scrollRef(element);
    },
    [scrollRef],
  );

  useEffect(() => {
    onCurrentPageChange?.(current);
  }, [current, onCurrentPageChange]);

  // Reads where the reader is from the layout: the page at the top, for the
  // zoom anchor, and the page showing most, for the toolbar. Runs on every
  // scroll and straight after a jump, so neither waits for a scroll event.
  const sync = useCallback(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    if (pagesRef.current.length !== pageCount) {
      pagesRef.current = pageElements(root);
    }
    const pages = pagesRef.current;
    if (pages.length === 0) {
      return;
    }
    // The anchor uses the same coordinates as the jumps and the restore:
    // page 0's top at 0.
    const origin = pages[0]?.offsetTop ?? 0;
    const y = root.scrollTop + origin;
    const index = Math.max(
      0,
      firstPast(pages, y, (page) => page.offsetTop) - 1,
    );
    const page = pages[index];
    if (page && page.offsetHeight > 0 && page.offsetWidth > 0) {
      anchorRef.current = {
        index,
        fraction: (y - page.offsetTop) / page.offsetHeight,
        across:
          (root.scrollLeft + root.clientWidth / 2 - page.offsetLeft) /
          page.offsetWidth,
      };
    }
    const jump = jumpRef.current;
    if (jump && Math.abs(root.scrollTop - jump.scrollTop) < 1) {
      setCurrent(jump.index);
    } else {
      jumpRef.current = null;
      setCurrent(mostVisiblePage(root, pages));
    }
  }, [pageCount]);

  // A taller or shorter viewer changes which page shows most without any
  // scroll event.
  useEffect(() => {
    const root = rootRef.current;
    if (!root || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => sync());
    observer.observe(root);
    return () => observer.disconnect();
  }, [sync]);

  // A zoom change resizes every page; keep the same spot of the same page at
  // the top, and the same spot across it in the middle (the browser clamps
  // this to 0 when the pages fit across). The pages took their new size from
  // their style at commit.
  const previousZoom = useRef(zoom);
  useLayoutEffect(() => {
    if (previousZoom.current === zoom) {
      return;
    }
    previousZoom.current = zoom;
    const root = rootRef.current;
    const { index, fraction, across } = anchorRef.current;
    const page = root && pageElement(root, index);
    if (root && page) {
      root.scrollTop = pageTop(root, page) + fraction * page.offsetHeight;
      root.scrollLeft =
        page.offsetLeft + across * page.offsetWidth - root.clientWidth / 2;
      sync();
    }
  }, [zoom, sync]);

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage(index) {
        const root = rootRef.current;
        const clamped = Math.min(Math.max(0, index), pageCount - 1);
        const page = root && pageElement(root, clamped);
        if (root && page) {
          root.scrollTop = pageTop(root, page);
          jumpRef.current = { index: clamped, scrollTop: root.scrollTop };
          sync();
        }
      },
      scrollToHighlight(id) {
        const highlight = highlights.find((candidate) => candidate.id === id);
        const root = rootRef.current;
        const page = highlight && root && pageElement(root, highlight.page);
        if (!highlight || !root || !page) {
          return false;
        }
        // A highlight is not a page jump: drop any earlier jump, or a scroll
        // clamped at the same end would still report the jumped-to page.
        jumpRef.current = null;
        const centreY = (highlight.y + highlight.h / 2) * page.offsetHeight;
        // The page's own top, padding included: centred exactly, unlike a
        // page jump, which keeps the gap above the page.
        root.scrollTop = page.offsetTop + centreY - root.clientHeight / 2;
        if (highlight.variant === "box") {
          const centreX = (highlight.x + highlight.w / 2) * page.offsetWidth;
          root.scrollLeft = page.offsetLeft + centreX - root.clientWidth / 2;
        }
        sync();
        return true;
      },
    }),
    [highlights, pageCount, sync],
  );

  // Only the page holding the active highlight hears its id, so moving the
  // active highlight re-renders the page it left and the page it reached.
  const activePage = useMemo(
    () =>
      activeHighlightId == null
        ? null
        : (highlights.find((highlight) => highlight.id === activeHighlightId)
            ?.page ?? null),
    [highlights, activeHighlightId],
  );
  const pixelRatio = useDevicePixelRatio();

  // A scrollable region must be focusable for keyboard users (WCAG 2.1.1),
  // and its focus is where the viewer's paging and zoom keys are read.
  return (
    // biome-ignore lint/a11y/noNoninteractiveElementInteractions: the keys belong to the focusable scroll region
    <section
      ref={setRoot}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable
      tabIndex={0}
      aria-label="Document pages"
      onScroll={sync}
      onKeyDown={onKeyDown}
      className={cn(
        "ui:relative ui:h-full ui:overflow-auto ui:bg-muted ui:focus-visible:focus-ring",
        className,
      )}
    >
      {/* w-max with min-w-full: centred while pages fit, scrollable both ways
          once a zoomed page is wider than the viewer. */}
      <div className="ui:mx-auto ui:flex ui:w-max ui:min-w-full ui:flex-col ui:items-center ui:gap-4 ui:p-4">
        {pageSizes.map((size, index) => (
          <PdfPage
            // Pages never reorder within a document.
            // biome-ignore lint/suspicious/noArrayIndexKey: the index is the page's identity
            key={index}
            document={document}
            index={index}
            pageCount={pageSizes.length}
            size={size}
            zoom={zoom}
            rendered={rendered.has(index)}
            pixelRatio={pixelRatio}
            observe={observePage}
            highlights={byPage.get(index) ?? NO_HIGHLIGHTS}
            activeHighlightId={index === activePage ? activeHighlightId : null}
            onHighlightClick={onHighlightClick}
            renderOverlay={renderPageOverlay}
          />
        ))}
      </div>
    </section>
  );
}
