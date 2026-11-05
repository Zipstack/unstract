import { type Highlight, NO_HIGHLIGHTS } from "@v1/lib/pdf/highlights";
import type { PageSize } from "@v1/lib/pdf/types";
import { CSS_PIXELS_PER_POINT, pageCssSize } from "@v1/lib/pdf/windowing";
import {
  type KeyboardEvent,
  type Ref,
  type SyntheticEvent,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { HighlightLayer } from "./HighlightLayer";
import type { PdfPageListHandle } from "./PdfPageList";
import { PAGE_FRAME_CLASS } from "./pageFrame";
import { ViewerStatus } from "./ViewerStatus";

export interface ImageViewProps {
  url: string;
  alt?: string;
  /** 1 shows the image at its natural size. */
  zoom: number;
  /** Highlights on page 0, in fractions of the image. */
  highlights?: readonly Highlight[];
  activeHighlightId?: string | null;
  onHighlightClick?: (highlight: Highlight) => void;
  /**
   * The image's size once loaded, in PDF points, so the viewer can fit it the
   * same way as a page.
   */
  onLoadSize?: (size: PageSize) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  ref?: Ref<PdfPageListHandle>;
}

type LoadState =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; size: PageSize };

/** An image as a one-page document: the same zoom, highlights and scrolling. */
export function ImageView({
  url,
  alt = "Document image",
  zoom,
  highlights = NO_HIGHLIGHTS,
  activeHighlightId,
  onHighlightClick,
  onLoadSize,
  onKeyDown,
  ref,
}: ImageViewProps) {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  // A new URL is a new image: forget the last one's size and state while
  // rendering, so it is never laid out at the old size.
  const [shownUrl, setShownUrl] = useState(url);
  if (shownUrl !== url) {
    setShownUrl(url);
    setLoad({ status: "loading" });
  }
  const rootRef = useRef<HTMLElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  // The point of the image at the viewport's centre, as fractions of the
  // image, so a zoom keeps the reader on the same spot.
  const anchorRef = useRef({ x: 0.5, y: 0 });
  const ready = load.status === "ready";
  // An image is one page: highlights for any other page are not drawn.
  const pageHighlights = useMemo(
    () => highlights.filter((highlight) => highlight.page === 0),
    [highlights],
  );
  const css = load.status === "ready" ? pageCssSize(load.size, zoom) : null;

  const readAnchor = useCallback(() => {
    const root = rootRef.current;
    const frame = frameRef.current;
    if (
      !root ||
      !frame ||
      frame.offsetWidth === 0 ||
      frame.offsetHeight === 0
    ) {
      return;
    }
    anchorRef.current = {
      x:
        (root.scrollLeft + root.clientWidth / 2 - frame.offsetLeft) /
        frame.offsetWidth,
      y:
        (root.scrollTop + root.clientHeight / 2 - frame.offsetTop) /
        frame.offsetHeight,
    };
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage() {
        if (rootRef.current) {
          rootRef.current.scrollTop = 0;
          readAnchor();
        }
      },
      scrollToHighlight(id) {
        const highlight = pageHighlights.find(
          (candidate) => candidate.id === id,
        );
        const root = rootRef.current;
        const frame = frameRef.current;
        // Until the image has its size the frame is a placeholder: say not
        // yet, so the viewer tries again once it has loaded.
        if (!highlight || !root || !frame || !ready) {
          return false;
        }
        root.scrollTop =
          frame.offsetTop +
          (highlight.y + highlight.h / 2) * frame.offsetHeight -
          root.clientHeight / 2;
        // A line spans the image, so only a box moves the view across; a
        // line keeps the reader's horizontal place, as on a PDF page.
        if (highlight.variant === "box") {
          root.scrollLeft =
            frame.offsetLeft +
            (highlight.x + highlight.w / 2) * frame.offsetWidth -
            root.clientWidth / 2;
        }
        readAnchor();
        return true;
      },
    }),
    [pageHighlights, ready, readAnchor],
  );

  // A zoom resizes the frame; put the same spot back at the centre. The frame
  // took its new size from its style at commit.
  // Once the image is first laid out, the anchor is wherever the view is,
  // not a guess.
  const previousZoom = useRef(zoom);
  const wasReady = useRef(ready);
  useLayoutEffect(() => {
    const justLoaded = ready && !wasReady.current;
    wasReady.current = ready;
    const zoomed = previousZoom.current !== zoom;
    previousZoom.current = zoom;
    if (justLoaded) {
      readAnchor();
      return;
    }
    const root = rootRef.current;
    const frame = frameRef.current;
    if (!zoomed || !root || !frame || !ready) {
      return;
    }
    const { x, y } = anchorRef.current;
    root.scrollLeft =
      frame.offsetLeft + x * frame.offsetWidth - root.clientWidth / 2;
    root.scrollTop =
      frame.offsetTop + y * frame.offsetHeight - root.clientHeight / 2;
  }, [zoom, ready, readAnchor]);

  const onLoad = (event: SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth, naturalHeight } = event.currentTarget;
    // Natural pixels as points, so zoom 1 shows the image pixel for pixel.
    const size = {
      width: naturalWidth / CSS_PIXELS_PER_POINT,
      height: naturalHeight / CSS_PIXELS_PER_POINT,
    };
    setLoad({ status: "ready", size });
    onLoadSize?.(size);
  };

  if (load.status === "failed") {
    return (
      <ViewerStatus
        state={{ status: "failed", message: "The image didn't load." }}
        onRetry={() => {
          setLoad({ status: "loading" });
          setAttempt((count) => count + 1);
        }}
        onSubmitPassword={() => undefined}
      />
    );
  }

  return (
    // biome-ignore lint/a11y/noNoninteractiveElementInteractions: the keys belong to the focusable scroll region
    <section
      ref={rootRef}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable
      tabIndex={0}
      // The region names the viewer; the image's alt names the image, so a
      // screen reader does not hear the same words twice.
      aria-label="Image viewer"
      onKeyDown={onKeyDown}
      onScroll={readAnchor}
      className="ui:relative ui:h-full ui:overflow-auto ui:bg-muted ui:focus-visible:focus-ring"
    >
      {load.status === "loading" && (
        <ViewerStatus
          state={load}
          onRetry={() => undefined}
          onSubmitPassword={() => undefined}
        />
      )}
      <div className="ui:mx-auto ui:flex ui:w-max ui:min-w-full ui:flex-col ui:items-center ui:p-4">
        <div
          ref={frameRef}
          // Hidden and out of the flow until the image has a size.
          className={css ? PAGE_FRAME_CLASS : "ui:invisible ui:absolute"}
          style={{
            "--page-width": css ? `${css.width}px` : undefined,
            "--page-height": css ? `${css.height}px` : undefined,
          }}
        >
          {/* biome-ignore lint/a11y/noNoninteractiveElementInteractions: load and error are not user interactions */}
          <img
            key={attempt}
            src={url}
            alt={alt}
            onLoad={onLoad}
            onError={() => setLoad({ status: "failed" })}
            className="ui:block ui:size-full"
          />
          <HighlightLayer
            highlights={pageHighlights}
            activeId={activeHighlightId}
            onHighlightClick={onHighlightClick}
          />
        </div>
      </div>
    </section>
  );
}
