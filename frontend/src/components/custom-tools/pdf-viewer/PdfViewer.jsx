import { useEffect, useRef, useMemo } from "react";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import PropTypes from "prop-types";
import { highlightPlugin } from "@react-pdf-viewer/highlight";
import "@react-pdf-viewer/highlight/lib/styles/index.css";
import "./Highlight.css";

let RenderHighlights;
try {
  RenderHighlights =
    require("../../../plugins/pdf-highlight/RenderHighlights").RenderHighlights;
} catch (err) {
  // Do nothing, no plugin will be loaded.
}

function PdfViewer({ fileUrl, highlightData, currentHighlightIndex }) {
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;
  const parentRef = useRef(null);
  function removeZerosAndDeleteIfAllZero(highlightData) {
    return highlightData?.filter((innerArray) => {
      return (
        Array.isArray(innerArray) && innerArray.some((value) => value !== 0)
      );
    });
  }

  const processHighlightData = highlightData
    ? removeZerosAndDeleteIfAllZero(highlightData)
    : [];

  const processedHighlightData =
    processHighlightData?.length > 0 ? processHighlightData : [[0, 0, 0, 0]];

  const highlightPluginInstance = useMemo(() => {
    if (
      RenderHighlights &&
      Array.isArray(processedHighlightData) &&
      processedHighlightData?.length > 0
    ) {
      // Only pass the current highlight to render
      const currentHighlight =
        currentHighlightIndex !== undefined &&
        currentHighlightIndex < processedHighlightData.length
          ? [processedHighlightData[currentHighlightIndex]]
          : processedHighlightData;

      return highlightPlugin({
        renderHighlights: (props) => (
          <RenderHighlights {...props} highlightData={currentHighlight} />
        ),
      });
    }
    return "";
  }, [RenderHighlights, processedHighlightData, currentHighlightIndex]);

  // Jump to page when highlightData changes or when navigating through highlights
  useEffect(() => {
    const cleanedHighlightData = removeZerosAndDeleteIfAllZero(highlightData);
    if (cleanedHighlightData && cleanedHighlightData.length > 0) {
      // Use currentHighlightIndex if provided, otherwise default to first highlight
      const index =
        currentHighlightIndex !== undefined &&
        currentHighlightIndex < cleanedHighlightData.length
          ? currentHighlightIndex
          : 0;
      const pageNumber = cleanedHighlightData[index][0]; // Get page number from current highlight

      console.log("[PDF Navigation] Jumping to page:", {
        currentIndex: index,
        pageNumber: pageNumber,
        totalHighlights: cleanedHighlightData.length,
      });

      if (pageNumber !== null && pageNumber !== undefined && jumpToPage) {
        setTimeout(() => {
          jumpToPage(pageNumber); // jumpToPage is 0-indexed
        }, 100); // Add a slight delay to ensure proper page rendering
      }
    }
  }, [highlightData, jumpToPage, currentHighlightIndex]); // Changed dependency to highlightData instead of processedHighlightData

  return (
    <div ref={parentRef} className="doc-manager-body">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js">
        <Viewer
          fileUrl={fileUrl}
          plugins={[
            newPlugin,
            pageNavigationPluginInstance,
            highlightPluginInstance,
          ]}
        />
      </Worker>
    </div>
  );
}

PdfViewer.propTypes = {
  fileUrl: PropTypes.any,
  highlightData: PropTypes.array,
  currentHighlightIndex: PropTypes.number,
};

export { PdfViewer };
