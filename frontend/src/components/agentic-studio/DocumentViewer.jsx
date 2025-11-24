import { useState, useEffect } from "react";
import { Tabs, Spin, Typography, Empty } from "antd";
import { FileTextOutlined, FilePdfOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";

import { documentsApi, showApiError } from "../../helpers/agentic-api";

const { Text } = Typography;

function DocumentViewer({ projectId, document, onDocumentUpdate }) {
  const [activeTab, setActiveTab] = useState("pdf");
  const [rawText, setRawText] = useState(null);
  const [loadingRawText, setLoadingRawText] = useState(false);
  const [pdfUrl, setPdfUrl] = useState(null);

  useEffect(() => {
    if (document) {
      // Use the file_url provided by the backend
      if (document.file_url) {
        // Use relative URL - the browser will resolve it correctly
        // file_url should be a path like /api/v1/unstract/{orgId}/agentic/projects/{projectId}/documents/{docId}/file/
        setPdfUrl(document.file_url);
      } else {
        console.error("Document does not have a file_url", document);
        setPdfUrl(null);
      }
    }
  }, [document]);

  useEffect(() => {
    if (activeTab === "raw-text" && document && !rawText) {
      loadRawText();
    }
  }, [activeTab, document]);

  const loadRawText = async () => {
    try {
      setLoadingRawText(true);
      const response = await documentsApi.getDocumentRawText(
        projectId,
        document.id
      );
      setRawText(response.raw_text || "No raw text available");
    } catch (error) {
      showApiError(error, "Failed to load raw text");
      setRawText("Failed to load raw text");
    } finally {
      setLoadingRawText(false);
    }
  };

  const tabItems = [
    {
      key: "pdf",
      label: (
        <span>
          <FilePdfOutlined /> PDF View
        </span>
      ),
      children: (
        <div
          style={{
            height: "calc(100vh - 350px)",
            overflow: "hidden",
            background: "#f5f5f5",
          }}
        >
          {pdfUrl ? (
            <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js">
              <div style={{ height: "100%", width: "100%" }}>
                <Viewer fileUrl={pdfUrl} />
              </div>
            </Worker>
          ) : (
            <Empty
              description="No PDF available"
              style={{ marginTop: "20%" }}
            />
          )}
        </div>
      ),
    },
    {
      key: "raw-text",
      label: (
        <span>
          <FileTextOutlined /> Raw Text
        </span>
      ),
      children: (
        <div
          style={{
            height: "calc(100vh - 350px)",
            overflow: "auto",
            background: "#f5f5f5",
            padding: "16px",
          }}
        >
          {loadingRawText ? (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <Spin size="large" />
            </div>
          ) : rawText ? (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordWrap: "break-word",
                fontFamily: "monospace",
                fontSize: "13px",
                lineHeight: "1.6",
                margin: 0,
                padding: "16px",
                background: "#fff",
                borderRadius: "4px",
                border: "1px solid #d9d9d9",
              }}
            >
              {rawText}
            </pre>
          ) : (
            <Empty description="No raw text available. Process the document first." />
          )}
        </div>
      ),
    },
  ];

  if (!document) {
    return (
      <Empty description="No document selected" style={{ marginTop: "20%" }} />
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "16px 16px 0", background: "#fff" }}>
        <Text strong style={{ fontSize: "16px" }}>
          {document.original_filename}
        </Text>
        {document.pages && (
          <Text type="secondary" style={{ marginLeft: "12px" }}>
            ({document.pages} pages)
          </Text>
        )}
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        style={{ flex: 1 }}
        tabBarStyle={{ padding: "0 16px", margin: 0 }}
      />
    </div>
  );
}

DocumentViewer.propTypes = {
  projectId: PropTypes.string.isRequired,
  document: PropTypes.object.isRequired,
  onDocumentUpdate: PropTypes.func,
};

export default DocumentViewer;
