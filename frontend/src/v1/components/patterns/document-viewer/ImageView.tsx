import type { Highlight } from "@v1/lib/pdf/highlights";
import type { PageSize } from "@v1/lib/pdf/types";
import { CSS_PIXELS_PER_POINT, pageCssSize } from "@v1/lib/pdf/windowing";
import {
  type KeyboardEvent,
  type Ref,
  type SyntheticEvent,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { HighlightLayer } from "./HighlightLayer";
import type { PdfPageListHandle } from "./PdfPageList";
import { ViewerStatus } from "./ViewerStatus";

const NO_HIGHLIGHTS: readonly Highlight[] = [];

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
  const rootRef = useRef<HTMLElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const css = load.status === "ready" ? pageCssSize(load.size, zoom) : null;

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage() {
        if (rootRef.current) {
          rootRef.current.scrollTop = 0;
        }
      },
      scrollToHighlight(id) {
        const highlight = highlights.find((candidate) => candidate.id === id);
        const root = rootRef.current;
        const frame = frameRef.current;
        if (!highlight || !root || !frame) {
          return false;
        }
        root.scrollTop =
          frame.offsetTop +
          (highlight.y + highlight.h / 2) * frame.offsetHeight -
          root.clientHeight / 2;
        root.scrollLeft =
          frame.offsetLeft +
          (highlight.x + highlight.w / 2) * frame.offsetWidth -
          root.clientWidth / 2;
        return true;
      },
    }),
    [highlights],
  );

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
      aria-label="Document image"
      onKeyDown={onKeyDown}
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
          className={
            load.status === "ready"
              ? "ui:relative ui:h-(--page-height) ui:w-(--page-width) ui:shrink-0 ui:bg-card ui:shadow-sm"
              : "ui:invisible ui:absolute"
          }
          // The image's size is runtime geometry: custom properties the classes read.
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
            highlights={highlights}
            activeId={activeHighlightId}
            onHighlightClick={onHighlightClick}
          />
        </div>
      </div>
    </section>
  );
}
