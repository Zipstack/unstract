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

function PdfViewer({ fileUrl, highlightData }) {
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;
  const parentRef = useRef(null);
  function removeZerosAndDeleteIfAllZero(highlightData) {
    if (Array.isArray(highlightData))
      return highlightData?.filter((innerArray) => {
        return (
          Array.isArray(innerArray) && innerArray?.some((value) => value !== 0)
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
      return highlightPlugin({
        renderHighlights: (props) => (
          <RenderHighlights {...props} highlightData={processedHighlightData} />
        ),
      });
    }
    return "";
  }, [RenderHighlights, processedHighlightData]);

  // Jump to page when highlightData changes
  useEffect(() => {
    highlightData = removeZerosAndDeleteIfAllZero(highlightData); // Removing zeros before checking the highlight data condition
    if (highlightData && highlightData.length > 0) {
      const pageNumber = highlightData[0][0]; // Assume highlightData[0][0] is the page number
      if (pageNumber !== null && jumpToPage) {
        setTimeout(() => {
          jumpToPage(pageNumber); // jumpToPage is 0-indexed, so subtract 1 if necessary
        }, 100); // Add a slight delay to ensure proper page rendering
      }
    }
  }, [processedHighlightData, jumpToPage]);

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
};

export { PdfViewer };
