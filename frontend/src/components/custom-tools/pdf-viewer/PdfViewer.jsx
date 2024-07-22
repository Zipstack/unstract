import { useRef } from "react";
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
  // Do nothing, No plugin will be loaded.
}

function PdfViewer({ fileUrl, highlightData }) {
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const parentRef = useRef(null);
  let highlightPluginInstance = "";
  if (RenderHighlights && highlightData) {
    highlightPluginInstance = highlightPlugin({
      renderHighlights: (props) => (
        <RenderHighlights {...props} highlightData={highlightData} />
      ),
    });
  }

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
