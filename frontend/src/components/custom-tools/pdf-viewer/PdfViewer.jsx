import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import PropTypes from "prop-types";
import { highlightPlugin } from "@react-pdf-viewer/highlight";
import { Result, Button } from "antd";
import { FileExclamationOutlined, ReloadOutlined } from "@ant-design/icons";

import "@react-pdf-viewer/highlight/lib/styles/index.css";
import "./Highlight.css";
import { PDF_WORKER_URL } from "../../../helpers/pdfWorkerConfig";

let RenderHighlights;
try {
  RenderHighlights =
    require("../../../plugins/pdf-highlight/RenderHighlights").RenderHighlights;
} catch (err) {
  // Do nothing, no plugin will be loaded.
}

function PdfViewer({ fileUrl, highlightData, currentHighlightIndex, onError }) {
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;
  const parentRef = useRef(null);

  // Retry key to force re-render when retrying
  const [retryKey, setRetryKey] = useState(0);
  const handleRetry = useCallback(() => {
    setRetryKey((prev) => prev + 1);
  }, []);

  // Render error fallback for PDF load failures
  const renderError = useCallback(
    (error) => {
      const errorMessage =
        error?.message ||
        "Failed to load PDF document. The file may be corrupted or inaccessible.";

      // Notify parent component of error if callback provided
      if (onError) {
        onError(error);
      }

      return (
        <div className="pdf-viewer-error">
          <Result
            icon={<FileExclamationOutlined style={{ color: "#ff4d4f" }} />}
            title="Failed to Load PDF"
            subTitle={errorMessage}
            extra={
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleRetry}
              >
                Retry
              </Button>
            }
          />
        </div>
      );
    },
    [onError, handleRetry]
  );

  function removeZerosAndDeleteIfAllZero(highlightData) {
    if (Array.isArray(highlightData))
      return highlightData
        ?.filter((innerArray) => {
          if (!Array.isArray(innerArray)) return false;
          // Strip 5th element (confidence) if present, keep only first 4 elements
          const coordsOnly =
            innerArray.length >= 5 ? innerArray.slice(0, 4) : innerArray;
          return coordsOnly.some((value) => value !== 0);
        })
        .map((innerArray) => {
          // Return only the first 4 elements (strip confidence)
          return innerArray.length >= 5 ? innerArray.slice(0, 4) : innerArray;
        });
  }

  const processHighlightData = highlightData
    ? removeZerosAndDeleteIfAllZero(highlightData)
    : [];

  const processedHighlightData =
    processHighlightData?.length > 0 ? processHighlightData : [[0, 0, 0, 0]];

  // Determine current highlight data
  const currentHighlightData = useMemo(() => {
    if (
      RenderHighlights &&
      Array.isArray(processedHighlightData) &&
      processedHighlightData?.length > 0
    ) {
      return currentHighlightIndex !== null &&
        currentHighlightIndex < processedHighlightData.length
        ? [processedHighlightData[currentHighlightIndex]]
        : processedHighlightData;
    }
    return null;
  }, [processedHighlightData, currentHighlightIndex]);

  // Always create both plugins at top level to maintain hook order
  const baseHighlightPlugin = highlightPlugin();
  const customHighlightPlugin = highlightPlugin({
    renderHighlights:
      currentHighlightData && RenderHighlights
        ? (props) => (
            <RenderHighlights {...props} highlightData={currentHighlightData} />
          )
        : undefined,
  });

  // Choose which plugin to use
  const highlightPluginInstance = currentHighlightData
    ? customHighlightPlugin
    : baseHighlightPlugin;

  // Jump to page when highlightData changes or when navigating through highlights
  useEffect(() => {
    const cleanedHighlightData = removeZerosAndDeleteIfAllZero(highlightData);
    if (cleanedHighlightData && cleanedHighlightData.length > 0) {
      // Use currentHighlightIndex if provided, otherwise default to first highlight
      const index =
        currentHighlightIndex !== null &&
        currentHighlightIndex < cleanedHighlightData.length
          ? currentHighlightIndex
          : 0;
      const pageNumber = cleanedHighlightData[index][0]; // Get page number from current highlight

      if (pageNumber !== null && pageNumber !== undefined && jumpToPage) {
        setTimeout(() => {
          jumpToPage(pageNumber); // jumpToPage is 0-indexed
        }, 100); // Add a slight delay to ensure proper page rendering
      }
    }
  }, [highlightData, jumpToPage, currentHighlightIndex]); // Changed dependency to highlightData instead of processedHighlightData

  // Show empty state when no URL is provided
  if (!fileUrl) {
    return (
      <div ref={parentRef} className="doc-manager-body pdf-viewer-error">
        <Result
          icon={<FileExclamationOutlined style={{ color: "#faad14" }} />}
          title="No PDF Available"
          subTitle="The PDF document URL is not available. Please ensure the document has been processed correctly."
        />
      </div>
    );
  }

  return (
    <div ref={parentRef} className="doc-manager-body" key={retryKey}>
      <Worker workerUrl={PDF_WORKER_URL}>
        <Viewer
          fileUrl={fileUrl}
          plugins={[
            newPlugin,
            pageNavigationPluginInstance,
            highlightPluginInstance,
          ]}
          renderError={renderError}
        />
      </Worker>
    </div>
  );
}

PdfViewer.propTypes = {
  fileUrl: PropTypes.any,
  highlightData: PropTypes.array,
  currentHighlightIndex: PropTypes.number,
  onError: PropTypes.func,
};

export { PdfViewer };
