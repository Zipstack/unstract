import PropTypes from "prop-types";
import { useState, useImperativeHandle, forwardRef, useCallback } from "react";
import { Viewer, Worker, SpecialZoomLevel } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import "./PdfViewer.css";

// Configure PDF.js worker - using same version as package.json
const PDFJS_VERSION = "3.4.120";
const WORKER_URL = `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.js`;

const PdfViewer = forwardRef(
  (
    {
      url,
      onLoadSuccess,
      className = "",
      highlights = [],
      activeHighlightIndex = -1,
      showAllHighlights = true,
      onHighlightClick,
    },
    ref
  ) => {
    const [, setCurrentPage] = useState(0);
    const defaultLayoutPluginInstance = defaultLayoutPlugin();

    // Helper to get CSS properties for highlight
    const getCssProperties = (coords, isActive) => {
      // coords format: [page, x, y, width, height] (all percentages 0-100)
      const [, x, y, width, height] = coords;

      return {
        position: "absolute",
        left: `${x}%`,
        top: `${y}%`,
        width: `${width}%`,
        height: `${height}%`,
        backgroundColor: isActive
          ? "rgba(255, 235, 59, 0.5)"
          : "rgba(33, 150, 243, 0.3)",
        border: isActive ? "2px solid #FBC02D" : "1px solid #1976D2",
        pointerEvents: "auto",
        cursor: "pointer",
        transition: "all 0.2s ease",
        zIndex: isActive ? 2 : 1,
      };
    };

    // Filter highlights for specific page
    const filterHighlightsForPage = (allHighlights, pageIndex) => {
      return allHighlights.filter((coords) => coords[0] === pageIndex);
    };

    // Create highlight rendering plugin
    const highlightPlugin = {
      renderPageLayer: (pluginProps) => {
        if (!highlights || highlights.length === 0) {
          return <></>;
        }

        const pageHighlights = filterHighlightsForPage(
          highlights,
          pluginProps.pageIndex
        );

        if (pageHighlights.length === 0) {
          return null;
        }

        return (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              pointerEvents: "auto",
            }}
          >
            {pageHighlights.map((coords, localIndex) => {
              // Find global index in original highlights array
              const globalIndex = highlights.findIndex(
                (h) =>
                  h[0] === coords[0] && h[1] === coords[1] && h[2] === coords[2]
              );

              const isActive = globalIndex === activeHighlightIndex;

              // If showAllHighlights is false, only render active highlight
              if (!showAllHighlights && !isActive) {
                return null;
              }

              // Get CSS properties for this highlight
              const style = getCssProperties(coords, isActive);

              return (
                <div
                  key={`highlight-${pluginProps.pageIndex}-${localIndex}`}
                  data-highlight-id={`highlight-${globalIndex}`}
                  style={style}
                  className={`pdf-highlight ${isActive ? "active" : ""}`}
                  onClick={() =>
                    onHighlightClick && onHighlightClick(globalIndex)
                  }
                  role="button"
                  tabIndex={0}
                  aria-label={`Highlight ${globalIndex + 1}`}
                />
              );
            })}
          </div>
        );
      },
    };

    // Handle document load
    const handleDocumentLoad = useCallback(
      (e) => {
        const { doc } = e;
        const numPages = doc.numPages;

        if (onLoadSuccess) {
          onLoadSuccess(numPages);
        }
      },
      [onLoadSuccess]
    );

    // Handle page change
    const handlePageChange = useCallback((e) => {
      setCurrentPage(e.currentPage);
    }, []);

    // Expose ref methods
    useImperativeHandle(ref, () => ({
      scrollToPage: (page) => {
        // @react-pdf-viewer uses 0-indexed pages internally
        const pageIndex = page - 1;
        if (pageIndex >= 0) {
          setCurrentPage(pageIndex);
        }
      },
      jumpToHighlight: (highlightIndex) => {
        if (highlightIndex >= 0 && highlightIndex < highlights.length) {
          const highlight = highlights[highlightIndex];
          const pageIndex = highlight[0]; // Page is first element in coordinate array
          setCurrentPage(pageIndex);
        }
      },
      scrollToHighlightPosition: (highlightIndex) => {
        if (highlightIndex >= 0 && highlightIndex < highlights.length) {
          const highlight = highlights[highlightIndex];
          const pageIndex = highlight[0]; // Page is first element in coordinate array

          // First, jump to the page
          setCurrentPage(pageIndex);

          // Then, after a delay to ensure page and highlights are rendered,
          // scroll to the exact highlight position
          setTimeout(() => {
            const highlightElement = document.querySelector(
              `[data-highlight-id="highlight-${highlightIndex}"]`
            );

            if (highlightElement) {
              highlightElement.scrollIntoView({
                behavior: "smooth",
                block: "center",
                inline: "nearest",
              });
            } else {
              console.warn(
                `Highlight element not found for index ${highlightIndex}`
              );
            }
          }, 200); // 200ms delay to ensure page + highlight overlays are rendered
        }
      },
    }));

    if (!url) {
      return (
        <div className="pdf-viewer-empty">
          <p>No PDF selected</p>
        </div>
      );
    }

    return (
      <div className={`pdf-viewer-container ${className}`}>
        <Worker workerUrl={WORKER_URL}>
          <Viewer
            fileUrl={url}
            plugins={[defaultLayoutPluginInstance, highlightPlugin]}
            onDocumentLoad={handleDocumentLoad}
            onPageChange={handlePageChange}
            defaultScale={SpecialZoomLevel.PageFit}
            withCredentials={true}
          />
        </Worker>
      </div>
    );
  }
);

PdfViewer.displayName = "PdfViewer";

PdfViewer.propTypes = {
  url: PropTypes.string,
  onLoadSuccess: PropTypes.func,
  className: PropTypes.string,
  highlights: PropTypes.array,
  activeHighlightIndex: PropTypes.number,
  showAllHighlights: PropTypes.bool,
  onHighlightClick: PropTypes.func,
};

export default PdfViewer;
