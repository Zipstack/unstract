import type { PageSize } from "@v1/lib/pdf/types";
import {
  CSS_PIXELS_PER_POINT,
  canvasPixelRatio,
  pageCssSize,
} from "@v1/lib/pdf/windowing";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import { memo, type ReactNode, useEffect, useRef, useState } from "react";

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
  observe: (element: HTMLElement | null) => (() => void) | undefined;
  /** Drawn over the page, in a box the same size as the page. */
  children?: ReactNode;
}

type RenderState = "idle" | "rendering" | "rendered" | "error";

function isCancellation(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "RenderingCancelledException"
  );
}

/**
 * One page: a placeholder sized from the page's own dimensions, and a canvas
 * only while the page is inside the render window. Leaving the window, or a
 * zoom change, cancels any render in flight and frees the canvas.
 */
export const PdfPage = memo(function PdfPage({
  document,
  index,
  pageCount,
  size,
  zoom,
  rendered,
  observe,
  children,
}: PdfPageProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [state, setState] = useState<RenderState>("idle");
  const css = pageCssSize(size, zoom);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!rendered || canvas === null) {
      return;
    }
    let cancelled = false;
    let page: PDFPageProxy | null = null;
    let task: RenderTask | null = null;
    // Wait a frame: during a fast scroll the page has usually left the window
    // again by then, and nothing is drawn for it at all.
    const frame = requestAnimationFrame(() => {
      void (async () => {
        try {
          page = await document.getPage(index + 1);
          if (cancelled) {
            return;
          }
          const viewport = page.getViewport({
            scale: zoom * CSS_PIXELS_PER_POINT,
          });
          const ratio = canvasPixelRatio(
            viewport.width,
            viewport.height,
            window.devicePixelRatio,
          );
          canvas.width = Math.floor(viewport.width * ratio);
          canvas.height = Math.floor(viewport.height * ratio);
          const context = canvas.getContext("2d");
          if (context === null) {
            setState("error");
            return;
          }
          setState("rendering");
          task = page.render({
            canvasContext: context,
            viewport,
            transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
          });
          await task.promise;
          if (!cancelled) {
            setState("rendered");
          }
        } catch (error) {
          if (!cancelled && !isCancellation(error)) {
            setState("error");
          }
        }
      })();
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      task?.cancel();
      page?.cleanup();
      // Zero the backing store now rather than waiting for garbage collection;
      // Safari in particular keeps it until then and caps the total.
      canvas.width = 0;
      canvas.height = 0;
      setState("idle");
    };
  }, [document, index, zoom, rendered]);

  return (
    <div
      ref={observe}
      data-page-index={index}
      data-render-state={state}
      role="img"
      aria-label={`Page ${index + 1} of ${pageCount}`}
      className="ui:relative ui:h-(--page-height) ui:w-(--page-width) ui:shrink-0 ui:bg-card ui:shadow-sm"
      // A page's size is runtime geometry, not a token: it goes through custom
      // properties, which the classes read.
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
      {children}
    </div>
  );
});
