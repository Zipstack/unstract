import { useElementSize } from "@v1/hooks/useElementSize";
import { usePdfDocument } from "@v1/hooks/usePdfDocument";
import { cn } from "@v1/lib/cn";
import type { Highlight } from "@v1/lib/pdf/highlights";
import { viewerKeyAction } from "@v1/lib/pdf/keyboard";
import { pdfSourceKey } from "@v1/lib/pdf/pdfjs";
import type { PageSize, PdfSource } from "@v1/lib/pdf/types";
import {
  fitZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  type ZoomMode,
  zoomIn,
  zoomOut,
} from "@v1/lib/pdf/zoom";
import {
  type KeyboardEvent,
  type Ref,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { PdfPageList, type PdfPageListHandle } from "./PdfPageList";
import { ViewerStatus } from "./ViewerStatus";
import { ViewerToolbar } from "./ViewerToolbar";

export interface DocumentViewerHandle {
  /** Scrolls a 0-based page to the top. Waits for the document if it is loading. */
  scrollToPage: (index: number) => void;
  /**
   * Centres a highlight. Waits for the document if it is loading, and for the
   * highlight if it is not in `highlights` yet.
   */
  scrollToHighlight: (id: string) => void;
}

export interface DocumentViewerProps {
  source: PdfSource | null;
  highlights?: readonly Highlight[];
  /** Shown in the active tone and scrolled into view when it changes. */
  activeHighlightId?: string | null;
  onHighlightClick?: (highlight: Highlight) => void;
  /** A zoom level (1 is 100%) or a fit; fit width by default. */
  initialZoom?: number | Exclude<ZoomMode, "custom">;
  className?: string;
  ref?: Ref<DocumentViewerHandle>;
}

type ScrollRequest =
  | { kind: "page"; index: number }
  | { kind: "highlight"; id: string };

interface ZoomState {
  mode: ZoomMode;
  /** The level in custom mode; ignored while fitting. */
  level: number;
}

/**
 * Room around a fitted page, in CSS px: the list's padding on both sides plus
 * a vertical scrollbar, so fitting never causes a horizontal scrollbar.
 */
const FIT_GUTTER = 48;

// Gives each opened document its own key, so a new one gets a fresh page list:
// back at the top, with no window or anchor left over from the last.
const documentKeys = new WeakMap<object, number>();
let nextDocumentKey = 0;
function documentKey(document: object): number {
  let key = documentKeys.get(document);
  if (key === undefined) {
    key = nextDocumentKey++;
    documentKeys.set(document, key);
  }
  return key;
}

function widest(pageSizes: readonly PageSize[]): PageSize | undefined {
  let best: PageSize | undefined;
  for (const size of pageSizes) {
    if (!best || size.width > best.width) {
      best = size;
    }
  }
  return best;
}

function initialZoomState(
  initial: DocumentViewerProps["initialZoom"],
): ZoomState {
  if (typeof initial === "number") {
    return { mode: "custom", level: initial };
  }
  return { mode: initial ?? "fit-width", level: 1 };
}

/**
 * A PDF with a toolbar: loads it, shows its states, and renders its pages with
 * highlights. Keys while the pages have focus: PageUp/PageDown, Home/End,
 * + and −.
 */
export function DocumentViewer({
  source,
  highlights,
  activeHighlightId,
  onHighlightClick,
  initialZoom,
  className,
  ref,
}: DocumentViewerProps) {
  const { state, retry, submitPassword } = usePdfDocument(source);
  const [zoomState, setZoomState] = useState(() =>
    initialZoomState(initialZoom),
  );
  const [pageIndex, setPageIndex] = useState(0);
  const [bodyRef, bodySize] = useElementSize<HTMLDivElement>();
  const listRef = useRef<PdfPageListHandle | null>(null);
  const pendingRef = useRef<ScrollRequest | null>(null);

  const ready = state.status === "ready";
  const pageSizes = ready ? state.pageSizes : undefined;
  const pageCount = pageSizes?.length ?? 0;

  const zoom = useMemo(() => {
    if (zoomState.mode === "custom" || !pageSizes || !bodySize) {
      return zoomState.level;
    }
    if (zoomState.mode === "fit-width") {
      const page = widest(pageSizes);
      return page
        ? fitZoom(page, bodySize.width, null, FIT_GUTTER)
        : zoomState.level;
    }
    // Fit page fits every page, not the current one: in a document that mixes
    // sizes, a zoom that followed the current page would rescale the whole
    // document each time scrolling crossed into a page of another size.
    let level = Number.POSITIVE_INFINITY;
    for (const page of pageSizes) {
      level = Math.min(
        level,
        fitZoom(page, bodySize.width, bodySize.height, FIT_GUTTER),
      );
    }
    return Number.isFinite(level) ? level : zoomState.level;
  }, [zoomState, pageSizes, bodySize]);

  // A request runs now if it can, or waits in pendingRef: for the pages while
  // loading, and for its highlight while that is not in the list yet. A newer
  // request replaces a waiting one.
  const run = useCallback((request: ScrollRequest) => {
    const list = listRef.current;
    if (!list) {
      pendingRef.current = request;
      return;
    }
    if (request.kind === "page") {
      pendingRef.current = null;
      list.scrollToPage(request.index);
    } else {
      pendingRef.current = list.scrollToHighlight(request.id) ? null : request;
    }
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage: (index) => run({ kind: "page", index }),
      scrollToHighlight: (id) => run({ kind: "highlight", id }),
    }),
    [run],
  );

  // A waiting request belongs to the document it was made for: another
  // source drops it rather than scrolling a document nobody asked about.
  const sourceKey = pdfSourceKey(source);
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs on each new source
  useEffect(() => {
    pendingRef.current = null;
  }, [sourceKey]);

  // A waiting request runs once the pages are laid out, and is tried again
  // when the highlights change, in case its highlight has arrived.
  // biome-ignore lint/correctness/useExhaustiveDependencies: retried on each new highlights list
  useEffect(() => {
    if (ready && pendingRef.current) {
      run(pendingRef.current);
    }
  }, [ready, highlights, run]);

  useEffect(() => {
    if (activeHighlightId) {
      run({ kind: "highlight", id: activeHighlightId });
    } else if (pendingRef.current?.kind === "highlight") {
      pendingRef.current = null;
    }
  }, [activeHighlightId, run]);

  const goToPage = useCallback(
    (index: number) => run({ kind: "page", index }),
    [run],
  );
  const zoomBy = useCallback(
    (step: (level: number) => number) =>
      setZoomState({ mode: "custom", level: step(zoom) }),
    [zoom],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const action = viewerKeyAction(event);
    if (action === null) {
      return;
    }
    event.preventDefault();
    switch (action) {
      case "previous-page":
        goToPage(pageIndex - 1);
        break;
      case "next-page":
        goToPage(pageIndex + 1);
        break;
      case "first-page":
        goToPage(0);
        break;
      case "last-page":
        goToPage(pageCount - 1);
        break;
      case "zoom-in":
        zoomBy(zoomIn);
        break;
      case "zoom-out":
        zoomBy(zoomOut);
        break;
    }
  };

  return (
    <div
      className={cn(
        "ui:flex ui:h-full ui:min-h-0 ui:flex-col ui:bg-background",
        className,
      )}
    >
      {ready && (
        <ViewerToolbar
          pageIndex={pageIndex}
          pageCount={pageCount}
          zoom={zoom}
          zoomMode={zoomState.mode}
          canZoomIn={zoom < MAX_ZOOM}
          canZoomOut={zoom > MIN_ZOOM}
          onPageChange={goToPage}
          onZoomIn={() => zoomBy(zoomIn)}
          onZoomOut={() => zoomBy(zoomOut)}
          onFitWidth={() => setZoomState({ mode: "fit-width", level: zoom })}
          onFitPage={() => setZoomState({ mode: "fit-page", level: zoom })}
        />
      )}
      <div ref={bodyRef} className="ui:min-h-0 ui:flex-1">
        {ready ? (
          <PdfPageList
            key={documentKey(state.document)}
            ref={listRef}
            document={state.document}
            pageSizes={state.pageSizes}
            zoom={zoom}
            highlights={highlights}
            activeHighlightId={activeHighlightId}
            onHighlightClick={onHighlightClick}
            onCurrentPageChange={setPageIndex}
            onKeyDown={onKeyDown}
          />
        ) : (
          <ViewerStatus
            state={state}
            onRetry={retry}
            onSubmitPassword={submitPassword}
          />
        )}
      </div>
    </div>
  );
}
