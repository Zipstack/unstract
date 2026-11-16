import type { Highlight } from "@v1/lib/pdf/highlights";
import { isRenderCancelled } from "@v1/lib/pdf/pdfjs";
import type { PageSize } from "@v1/lib/pdf/types";
import {
  CSS_PIXELS_PER_POINT,
  canvasPixelRatio,
  pageCssSize,
} from "@v1/lib/pdf/windowing";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import { memo, type ReactNode, useEffect, useRef, useState } from "react";
import { HighlightLayer } from "./HighlightLayer";
import { PAGE_FRAME_CLASS } from "./pageFrame";

export interface PdfPageProps {
  document: PDFDocumentProxy;
  /** 0-based page index. */
  index: number;
  pageCount: number;
  /** The page's size at scale 1, from `usePdfDocument`. */
  size: PageSize;
  /** 1 is 100%. */
  zoom: number;
  /** Whether this page is inside the render window and should hold a canvas. */
  rendered: boolean;
  /** The screen's device pixel ratio; a change redraws the page. */
  pixelRatio: number;
  observe: (element: HTMLElement | null) => (() => void) | undefined;
  /** This page's highlights. Keep the array stable: the page is memoised. */
  highlights: readonly Highlight[];
  /** The active highlight's id; the list gives it only to the page holding it. */
  activeHighlightId?: string | null;
  /** Keep it stable (useCallback): a new function re-renders every page. */
  onHighlightClick?: (highlight: Highlight) => void;
  /**
   * Drawn over the page, above its highlights, in a box the page's size;
   * receives the page's index. Called inside the page, so keep it stable
   * (useCallback): a new function re-renders every page.
   */
  renderOverlay?: (index: number) => ReactNode;
}

type RenderState = "idle" | "rendering" | "rendered" | "error";

/**
 * One page: a placeholder sized from the page's own dimensions, and a canvas
 * only while the page is inside the render window. A zoom change cancels any
 * render in flight and draws the new size off screen, keeping the old picture
 * up until the new one is ready; leaving the window frees the canvas.
 */
export const PdfPage = memo(function PdfPage({
  document,
  index,
  pageCount,
  size,
  zoom,
  rendered,
  pixelRatio,
  observe,
  highlights,
  activeHighlightId,
  onHighlightClick,
  renderOverlay,
}: PdfPageProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [state, setState] = useState<RenderState>("idle");
  // Bumped by Retry, to run the render again.
  const [attempt, setAttempt] = useState(0);
  // Whether the canvas holds a picture. It outlives a redraw (zoom keeps the
  // old picture until the new one lands) and ends when the canvas is freed.
  const [painted, setPainted] = useState(false);
  const css = pageCssSize(size, zoom);

  // Free the canvas when the page leaves the window or unmounts: zero its
  // backing store now rather than waiting for garbage collection; Safari in
  // particular keeps it until then and caps the total.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!rendered || canvas === null) {
      return;
    }
    return () => {
      canvas.width = 0;
      canvas.height = 0;
      setPainted(false);
    };
  }, [rendered]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: attempt runs the render again on Retry
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!rendered || canvas === null) {
      return;
    }
    let cancelled = false;
    let page: PDFPageProxy | null = null;
    let task: RenderTask | null = null;
    // Drawn off screen, then copied in one step, so the page keeps showing
    // its last picture (stretched, during a zoom) instead of going blank.
    const scratch = canvas.ownerDocument.createElement("canvas");
    // Wait a frame: during a fast scroll the page has usually left the window
    // again by then, and nothing is drawn for it at all.
    const frame = requestAnimationFrame(() => {
      setState("rendering");
      void (async () => {
        try {
          const loaded = await document.getPage(index + 1);
          if (cancelled) {
            // The effect's cleanup has already run without this page.
            loaded.cleanup();
            return;
          }
          page = loaded;
          const viewport = page.getViewport({
            scale: zoom * CSS_PIXELS_PER_POINT,
          });
          const ratio = canvasPixelRatio(
            viewport.width,
            viewport.height,
            pixelRatio,
          );
          scratch.width = Math.floor(viewport.width * ratio);
          scratch.height = Math.floor(viewport.height * ratio);
          const context = scratch.getContext("2d");
          if (context === null) {
            throw new Error("No 2D canvas context");
          }
          task = page.render({
            canvasContext: context,
            viewport,
            transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
          });
          await task.promise;
          if (cancelled) {
            return;
          }
          canvas.width = scratch.width;
          canvas.height = scratch.height;
          const shown = canvas.getContext("2d");
          if (shown === null) {
            throw new Error("No 2D canvas context");
          }
          shown.drawImage(scratch, 0, 0);
          setPainted(true);
          setState("rendered");
        } catch (error) {
          if (!cancelled && !isRenderCancelled(error)) {
            console.error(`Page ${index + 1} didn't render`, error);
            setState("error");
          }
        } finally {
          scratch.width = 0;
          scratch.height = 0;
        }
      })();
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      task?.cancel();
      page?.cleanup();
      scratch.width = 0;
      scratch.height = 0;
      setState("idle");
    };
  }, [document, index, zoom, rendered, pixelRatio, attempt]);

  return (
    <figure
      ref={observe}
      data-page-index={index}
      data-render-state={state}
      // A figure, not role="img": an img's children are presentational, which
      // would hide the highlight buttons from assistive technology.
      aria-label={`Page ${index + 1} of ${pageCount}`}
      className={PAGE_FRAME_CLASS}
      style={{
        "--page-width": `${css.width}px`,
        "--page-height": `${css.height}px`,
      }}
    >
      {rendered && (
        <canvas
          ref={canvasRef}
          className="ui:absolute ui:inset-0 ui:block ui:size-full"
        />
      )}
      <HighlightLayer
        highlights={highlights}
        activeId={activeHighlightId}
        onHighlightClick={onHighlightClick}
        painted={painted}
      />
      {renderOverlay?.(index)}
      {state === "error" && (
        <figcaption className="ui:absolute ui:inset-0 ui:flex ui:flex-col ui:items-center ui:justify-center ui:gap-2 ui:bg-card ui:text-body ui:text-muted-foreground">
          <span>This page didn't load.</span>
          <button
            type="button"
            className="ui:rounded-md ui:border ui:border-border ui:px-3 ui:py-1 ui:text-body ui:text-foreground ui:hover:bg-muted ui:focus-visible:focus-ring"
            onClick={() => setAttempt((count) => count + 1)}
          >
            Retry page {index + 1}
          </button>
        </figcaption>
      )}
    </figure>
  );
});
