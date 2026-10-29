import { usePageWindow } from "@v1/hooks/usePageWindow";
import { cn } from "@v1/lib/cn";
import { type Highlight, highlightsByPage } from "@v1/lib/pdf/highlights";
import type { PageSize } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { type ReactNode, useMemo } from "react";
import { PdfPage } from "./PdfPage";

const NO_HIGHLIGHTS: readonly Highlight[] = [];

export interface PdfPageListProps {
  document: PDFDocumentProxy;
  pageSizes: readonly PageSize[];
  /** 1 is 100%. */
  zoom: number;
  /** Highlights on any page, from the normalisers in `@v1/lib/pdf/highlights`. */
  highlights?: readonly Highlight[];
  activeHighlightId?: string | null;
  onHighlightClick?: (highlight: Highlight) => void;
  /** Drawn over a page, above its highlights; receives the 0-based page index. */
  renderPageOverlay?: (index: number) => ReactNode;
  className?: string;
}

/**
 * Every page of a document in one scrolling column. All pages are laid out at
 * their real size from the start, so the scrollbar is right, but only the
 * pages in view (± 2) hold a canvas.
 */
export function PdfPageList({
  document,
  pageSizes,
  zoom,
  highlights = NO_HIGHLIGHTS,
  activeHighlightId,
  onHighlightClick,
  renderPageOverlay,
  className,
}: PdfPageListProps) {
  const { scrollRef, observePage, rendered } = usePageWindow(pageSizes.length);
  const byPage = useMemo(() => highlightsByPage(highlights), [highlights]);
  return (
    <div
      ref={scrollRef}
      className={cn("ui:h-full ui:overflow-auto ui:bg-muted", className)}
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
    </div>
  );
}
