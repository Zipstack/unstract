import { usePageWindow } from "@v1/hooks/usePageWindow";
import { cn } from "@v1/lib/cn";
import { type Highlight, highlightsByPage } from "@v1/lib/pdf/highlights";
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

const NO_HIGHLIGHTS: readonly Highlight[] = [];

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
  onHighlightClick?: (highlight: Highlight) => void;
  /** Called with the 0-based page showing most of itself. */
  onCurrentPageChange?: (index: number) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  /** Drawn over a page, above its highlights; receives the 0-based page index. */
  renderPageOverlay?: (index: number) => ReactNode;
  className?: string;
  ref?: Ref<PdfPageListHandle>;
}

/** Where the reader is, kept across a zoom change: a page and a share of it. */
interface Anchor {
  index: number;
  fraction: number;
}

function pageElement(root: HTMLElement, index: number): HTMLElement | null {
  return root.querySelector<HTMLElement>(`[data-page-index="${index}"]`);
}

/** A page's top in scroll coordinates, so that page 0 sits at 0. */
function pageTop(root: HTMLElement, page: HTMLElement): number {
  const first = pageElement(root, 0);
  return page.offsetTop - (first?.offsetTop ?? 0);
}

/** The last page whose top is at or above `y`, found by halving the range. */
function pageAt(root: HTMLElement, pageCount: number, y: number): number {
  let low = 0;
  let high = pageCount - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    const page = pageElement(root, middle);
    if (page && pageTop(root, page) <= y) {
      low = middle;
    } else {
      high = middle - 1;
    }
  }
  return low;
}

/**
 * The page with the most of itself in view; the lower index wins a tie. Read
 * from the layout, so it is exact for pages of any height and right straight
 * after a jump, unlike intersection ratios, which only arrive at thresholds and
 * a frame later.
 */
function mostVisiblePage(root: HTMLElement, pageCount: number): number {
  const top = root.scrollTop;
  const bottom = top + root.clientHeight;
  let best = pageAt(root, pageCount, top);
  let bestShown = Number.NEGATIVE_INFINITY;
  for (let index = best; index < pageCount; index++) {
    const page = pageElement(root, index);
    if (!page) {
      break;
    }
    const pageStart = pageTop(root, page);
    if (pageStart >= bottom) {
      break;
    }
    const shown =
      Math.min(pageStart + page.offsetHeight, bottom) -
      Math.max(pageStart, top);
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
  const anchorRef = useRef<Anchor>({ index: 0, fraction: 0 });
  const [current, setCurrent] = useState(0);

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
    if (!root || pageCount === 0) {
      return;
    }
    const index = pageAt(root, pageCount, root.scrollTop);
    const page = pageElement(root, index);
    if (page && page.offsetHeight > 0) {
      anchorRef.current = {
        index,
        fraction: (root.scrollTop - pageTop(root, page)) / page.offsetHeight,
      };
    }
    setCurrent(mostVisiblePage(root, pageCount));
  }, [pageCount]);

  // A zoom change resizes every page; keep the same spot of the same page at
  // the top. The pages took their new size from their style at commit.
  const previousZoom = useRef(zoom);
  useLayoutEffect(() => {
    if (previousZoom.current === zoom) {
      return;
    }
    previousZoom.current = zoom;
    const root = rootRef.current;
    const { index, fraction } = anchorRef.current;
    const page = root && pageElement(root, index);
    if (root && page) {
      root.scrollTop = pageTop(root, page) + fraction * page.offsetHeight;
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
        const centreY = (highlight.y + highlight.h / 2) * page.offsetHeight;
        root.scrollTop = pageTop(root, page) + centreY - root.clientHeight / 2;
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
            observe={observePage}
            highlights={byPage.get(index) ?? NO_HIGHLIGHTS}
            activeHighlightId={activeHighlightId}
            onHighlightClick={onHighlightClick}
          >
            {renderPageOverlay?.(index)}
          </PdfPage>
        ))}
      </div>
    </section>
  );
}
