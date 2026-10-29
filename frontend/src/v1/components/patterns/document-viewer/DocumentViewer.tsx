import { useElementSize } from "@v1/hooks/useElementSize";
import { usePdfDocument } from "@v1/hooks/usePdfDocument";
import { cn } from "@v1/lib/cn";
import type { Highlight } from "@v1/lib/pdf/highlights";
import { viewerKeyAction } from "@v1/lib/pdf/keyboard";
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
  /** Centres a highlight. Waits for the document if it is loading. */
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
    const page =
      zoomState.mode === "fit-width"
        ? widest(pageSizes)
        : (pageSizes[pageIndex] ?? pageSizes[0]);
    if (!page) {
      return zoomState.level;
    }
    return fitZoom(
      page,
      bodySize.width,
      zoomState.mode === "fit-page" ? bodySize.height : null,
      FIT_GUTTER,
    );
  }, [zoomState, pageSizes, bodySize, pageIndex]);

  const run = useCallback((request: ScrollRequest) => {
    const list = listRef.current;
    if (!list) {
      pendingRef.current = request;
      return;
    }
    if (request.kind === "page") {
      list.scrollToPage(request.index);
    } else {
      list.scrollToHighlight(request.id);
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

  // Requests made while loading run once the pages are laid out.
  useEffect(() => {
    if (ready && pendingRef.current) {
      const request = pendingRef.current;
      pendingRef.current = null;
      run(request);
    }
  }, [ready, run]);

  useEffect(() => {
    if (activeHighlightId) {
      run({ kind: "highlight", id: activeHighlightId });
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
