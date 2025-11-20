import PropTypes from "prop-types";
import { useState } from "react";
import { Tabs } from "antd";

import PdfViewer from "./PdfViewer";
import MonacoEditor from "./MonacoEditor";

const DocumentManager = ({ projectId, document, highlights }) => {
  const [activeTab, setActiveTab] = useState("pdf");

  if (!document) {
    return (
      <div style={{ padding: "40px", textAlign: "center", color: "#999" }}>
        No document selected
      </div>
    );
  }

  const items = [
    {
      key: "pdf",
      label: "PDF View",
      children: (
        <div style={{ height: "calc(100vh - 200px)" }}>
          {/* TODO: Replace with actual document URL */}
          <PdfViewer
            url={`/api/projects/${projectId}/documents/${document.id}/download`}
            highlights={highlights || []}
          />
        </div>
      ),
    },
    {
      key: "raw",
      label: "Raw Text",
      children: (
        <div style={{ height: "calc(100vh - 200px)", overflow: "auto" }}>
          <MonacoEditor
            value={document.raw_text || "No raw text available"}
            language="plaintext"
            readOnly={true}
            height="100%"
          />
        </div>
      ),
    },
  ];

  return (
    <div style={{ height: "100%" }}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={items}
        style={{ height: "100%" }}
      />
    </div>
  );
};

DocumentManager.propTypes = {
  projectId: PropTypes.string.isRequired,
  document: PropTypes.object,
  highlights: PropTypes.array,
};

export default DocumentManager;
