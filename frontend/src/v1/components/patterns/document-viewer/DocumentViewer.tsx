import { useElementSize } from "@v1/hooks/useElementSize";
import { usePdfDocument } from "@v1/hooks/usePdfDocument";
import { cn } from "@v1/lib/cn";
import type { Highlight } from "@v1/lib/pdf/highlights";
import { viewerKeyAction } from "@v1/lib/pdf/keyboard";
import { pdfSourceKey } from "@v1/lib/pdf/pdfjs";
import {
  type DocumentSource,
  isPdfSource,
  type PageSize,
} from "@v1/lib/pdf/types";
import {
  clampZoom,
  fitZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  type ZoomMode,
  zoomIn,
  zoomOut,
} from "@v1/lib/pdf/zoom";
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
import { ImageView } from "./ImageView";
import { PdfPageList, type PdfPageListHandle } from "./PdfPageList";
import { type TextLineHighlight, TextView } from "./TextView";
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
  /** A PDF (URL or bytes), an image, or text. */
  source: DocumentSource | null;
  /** Page highlights, for a PDF or an image. */
  highlights?: readonly Highlight[];
  /** Line highlights, for text. */
  textHighlights?: readonly TextLineHighlight[];
  onTextHighlightClick?: (highlight: TextLineHighlight) => void;
  /** Shown at the start of the toolbar, whatever state the document is in. */
  switcher?: ReactNode;
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

/** A request that could not run yet, and what it was made for. */
interface PendingRequest {
  request: ScrollRequest;
  /** The source shown when it was made; another source drops it. */
  sourceKey: string;
  /** Made for `activeHighlightId`, so clearing that id drops it. */
  fromActive: boolean;
}

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
    return { mode: "custom", level: clampZoom(initial) };
  }
  return { mode: initial ?? "fit-width", level: 1 };
}

/**
 * A document with a toolbar. A PDF is loaded and rendered page by page, an
 * image as a single page, and text line by line; PDFs and images share zoom
 * and highlights. Keys while the content has focus: PageUp/PageDown,
 * Home/End, + and −.
 */
export function DocumentViewer({
  source,
  highlights,
  textHighlights,
  onTextHighlightClick,
  switcher,
  activeHighlightId,
  onHighlightClick,
  initialZoom,
  className,
  ref,
}: DocumentViewerProps) {
  const { state, retry, submitPassword } = usePdfDocument(
    isPdfSource(source) ? source : null,
  );
  // An image's size is known once it loads; kept with its URL so a new image
  // never borrows the last one's.
  const [image, setImage] = useState<{ url: string; size: PageSize } | null>(
    null,
  );
  const [zoomState, setZoomState] = useState(() =>
    initialZoomState(initialZoom),
  );
  const [pageIndex, setPageIndex] = useState(0);
  const [bodyRef, bodySize] = useElementSize<HTMLDivElement>();
  const listRef = useRef<PdfPageListHandle | null>(null);
  const pendingRef = useRef<PendingRequest | null>(null);

  const kind =
    source === null ? null : isPdfSource(source) ? "pdf" : source.kind;
  // Forget an image's size once another source is shown, so coming back to
  // it waits for its reload instead of treating it as ready straight away.
  const imageUrl = source?.kind === "image" ? source.url : null;
  const [shownImageUrl, setShownImageUrl] = useState(imageUrl);
  if (shownImageUrl !== imageUrl) {
    setShownImageUrl(imageUrl);
    setImage(null);
  }
  const imageSize =
    source?.kind === "image" && image?.url === source.url ? image.size : null;
  // A new text gets a fresh view, back at the top, like a new PDF or image.
  const text = source?.kind === "text" ? source.text : null;
  const [shownText, setShownText] = useState(text);
  const [textKey, setTextKey] = useState(0);
  if (shownText !== text) {
    setShownText(text);
    setTextKey((key) => key + 1);
  }
  const pdfReady = kind === "pdf" && state.status === "ready";
  const pageSizes = pdfReady
    ? state.pageSizes
    : imageSize
      ? [imageSize]
      : undefined;
  const pageCount = pageSizes?.length ?? 0;
  // When the content can take scroll requests.
  const ready = pdfReady || kind === "text" || imageSize !== null;
  // Which content a scroll request is for. A text is its own key.
  const sourceKey =
    source === null || isPdfSource(source)
      ? pdfSourceKey(source)
      : source.kind === "image"
        ? `image:${source.url}`
        : source.text;
  // Both kept in step at commit, before any parent's layout effect can make
  // a request, so a request is always judged against the source it was made
  // for, and a render React throws away cannot leave them stale.
  const readyRef = useRef(ready);
  const sourceKeyRef = useRef(sourceKey);
  useLayoutEffect(() => {
    readyRef.current = ready;
    sourceKeyRef.current = sourceKey;
  }, [ready, sourceKey]);

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
  const run = useCallback((request: ScrollRequest, fromActive = false) => {
    const list = listRef.current;
    // An image's view exists before the image has loaded, so wait for the
    // content to be ready, not just mounted.
    const wait = () => {
      pendingRef.current = {
        request,
        sourceKey: sourceKeyRef.current,
        fromActive,
      };
    };
    if (!list || !readyRef.current) {
      wait();
    } else if (request.kind === "page") {
      pendingRef.current = null;
      list.scrollToPage(request.index);
    } else if (list.scrollToHighlight(request.id)) {
      pendingRef.current = null;
    } else {
      wait();
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

  // A waiting request runs once the pages are laid out, and is tried again
  // when the highlights change, in case its highlight has arrived. One made
  // for another source is dropped rather than scrolling a document nobody
  // asked about.
  // biome-ignore lint/correctness/useExhaustiveDependencies: retried on each new highlights list
  useEffect(() => {
    const pending = pendingRef.current;
    if (!ready || !pending) {
      return;
    }
    if (pending.sourceKey === sourceKey) {
      run(pending.request, pending.fromActive);
    } else {
      pendingRef.current = null;
    }
  }, [ready, sourceKey, highlights, textHighlights, run]);

  // The active highlight is scrolled to when it changes, and again for each
  // new source, so one chosen before its document arrived is still found.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-armed on each new source
  useEffect(() => {
    if (activeHighlightId) {
      run({ kind: "highlight", id: activeHighlightId }, true);
    } else if (pendingRef.current?.fromActive) {
      pendingRef.current = null;
    }
  }, [activeHighlightId, sourceKey, run]);

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
    // Text and images are one scrolling page: their paging keys keep the
    // browser's own scrolling, and text has no zoom.
    const paging = action !== null && !action.startsWith("zoom");
    if (
      action === null ||
      (paging && kind !== "pdf") ||
      (!paging && kind === "text")
    ) {
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

  let content: ReactNode;
  if (source === null || kind === null) {
    content = (
      <ViewerStatus
        state={{ status: "empty" }}
        onRetry={retry}
        onSubmitPassword={submitPassword}
      />
    );
  } else if (source.kind === "text") {
    content = (
      <TextView
        key={textKey}
        ref={listRef}
        text={source.text}
        highlights={textHighlights}
        activeHighlightId={activeHighlightId}
        onHighlightClick={onTextHighlightClick}
        onKeyDown={onKeyDown}
      />
    );
  } else if (source.kind === "image") {
    const { url } = source;
    content = (
      <ImageView
        key={url}
        ref={listRef}
        url={url}
        alt={source.alt}
        zoom={zoom}
        highlights={highlights}
        activeHighlightId={activeHighlightId}
        onHighlightClick={onHighlightClick}
        onLoadSize={(size) => setImage({ url, size })}
        onKeyDown={onKeyDown}
      />
    );
  } else if (state.status === "ready") {
    content = (
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
    );
  } else {
    content = (
      <ViewerStatus
        state={state}
        onRetry={retry}
        onSubmitPassword={submitPassword}
      />
    );
  }

  const showPaging = pdfReady;
  const showZoom = pdfReady || imageSize !== null;

  return (
    <div
      className={cn(
        "ui:flex ui:h-full ui:min-h-0 ui:flex-col ui:bg-background",
        className,
      )}
    >
      {(showPaging || showZoom || switcher) && (
        <ViewerToolbar
          leading={switcher}
          showPaging={showPaging}
          showZoom={showZoom}
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
        {content}
      </div>
    </div>
  );
}
