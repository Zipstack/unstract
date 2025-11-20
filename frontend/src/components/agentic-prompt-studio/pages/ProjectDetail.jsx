import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Layout, Tabs, Button, Space, message } from "antd";
import {
  HistoryOutlined,
  SaveOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";

import { useMockApi } from "../hooks/useMockApi";
import DocumentManager from "../components/DocumentManager";
import MonacoEditor from "../components/MonacoEditor";
import DataRenderer from "../components/DataRenderer";
import AccuracyOverviewPanel from "../components/AccuracyOverviewPanel";
import SavePromptModal from "../components/SavePromptModal";
import PromptHistoryModal from "../components/PromptHistoryModal";
import ComparePromptsModal from "../components/ComparePromptsModal";
import "./ProjectDetail.css";

const { Content, Sider } = Layout;

const ProjectDetail = ({ projectId }) => {
  const [activeTab, setActiveTab] = useState("prompt");
  const [promptText, setPromptText] = useState("");
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [latestPrompt, setLatestPrompt] = useState(null);
  const [extractedData, setExtractedData] = useState(null);
  const [verifiedData, setVerifiedData] = useState(null);
  const [schema, setSchema] = useState(null);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [historyModalVisible, setHistoryModalVisible] = useState(false);
  const [compareModalVisible, setCompareModalVisible] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const api = useMockApi();

  useEffect(() => {
    if (projectId) {
      fetchProjectData();
    }
  }, [projectId]);

  const fetchProjectData = async () => {
    try {
      // Fetch latest prompt
      const prompt = await api.getLatestPrompt(projectId);
      setLatestPrompt(prompt);
      if (prompt) {
        setPromptText(prompt.prompt_text);
      }

      // Fetch documents
      const docs = await api.getDocuments(projectId);
      if (docs && docs.length > 0) {
        setSelectedDocument(docs[0]);

        // Fetch verified and extracted data for the first document
        const verified = await api.getVerifiedData(projectId, docs[0].id);
        setVerifiedData(verified);

        const extracted = await api.getExtractedData(projectId, docs[0].id);
        setExtractedData(extracted);
      }

      // Fetch schema
      const schemaData = await api.getSchema(projectId);
      setSchema(schemaData);
    } catch (error) {
      message.error("Failed to load project data");
      console.error("Fetch project data error:", error);
    }
  };

  const handlePromptChange = (value) => {
    setPromptText(value);
    setHasUnsavedChanges(true);
  };

  const handleSavePrompt = () => {
    setSaveModalVisible(true);
  };

  const handleRunExtraction = async () => {
    if (!selectedDocument) {
      message.warning("Please select a document first");
      return;
    }

    try {
      message.loading({ content: "Running extraction...", key: "extraction" });
      // TODO: Replace with actual API call
      await new Promise((resolve) => setTimeout(resolve, 2000));

      const extracted = await api.getExtractedData(
        projectId,
        selectedDocument.id
      );
      setExtractedData(extracted);

      message.success({ content: "Extraction completed", key: "extraction" });
      setActiveTab("extracted");
    } catch (error) {
      message.error({ content: "Extraction failed", key: "extraction" });
    }
  };

  const leftPanelItems = [
    {
      key: "status",
      label: "Status",
      children: (
        <div style={{ padding: "16px" }}>
          <AccuracyOverviewPanel projectId={projectId} />
          {/* TODO: Add document status table */}
          <p>Document processing status will be displayed here...</p>
        </div>
      ),
    },
    {
      key: "prompt",
      label: "Prompt",
      children: (
        <div
          style={{
            height: "calc(100vh - 200px)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ marginBottom: "12px" }}>
            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSavePrompt}
                disabled={!hasUnsavedChanges}
              >
                Save Version
              </Button>
              <Button
                icon={<HistoryOutlined />}
                onClick={() => setHistoryModalVisible(true)}
              >
                History
              </Button>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleRunExtraction}
              >
                Run Extraction
              </Button>
            </Space>
          </div>
          <div style={{ flex: 1 }}>
            <MonacoEditor
              value={promptText}
              onChange={handlePromptChange}
              language="plaintext"
              height="100%"
            />
          </div>
        </div>
      ),
    },
    {
      key: "verified",
      label: "Verified Data",
      children: (
        <div
          style={{
            padding: "16px",
            height: "calc(100vh - 200px)",
            overflow: "auto",
          }}
        >
          {verifiedData ? (
            <DataRenderer data={verifiedData.data} />
          ) : (
            <p style={{ color: "#999" }}>No verified data available</p>
          )}
        </div>
      ),
    },
    {
      key: "extracted",
      label: "Extracted Data",
      children: (
        <div
          style={{
            padding: "16px",
            height: "calc(100vh - 200px)",
            overflow: "auto",
          }}
        >
          {extractedData ? (
            <DataRenderer data={extractedData.data} />
          ) : (
            <p style={{ color: "#999" }}>
              No extracted data available. Run extraction first.
            </p>
          )}
        </div>
      ),
    },
    {
      key: "schema",
      label: "Schema",
      children: (
        <div style={{ padding: "16px", height: "calc(100vh - 200px)" }}>
          {schema ? (
            <MonacoEditor
              value={schema.json_schema}
              language="json"
              readOnly={true}
              height="100%"
            />
          ) : (
            <p style={{ color: "#999" }}>No schema available</p>
          )}
        </div>
      ),
    },
    {
      key: "settings",
      label: "Settings",
      children: (
        <div style={{ padding: "16px" }}>
          {/* TODO: Add project settings form */}
          <p>Project settings will be displayed here...</p>
        </div>
      ),
    },
  ];

  return (
    <div className="project-detail-container">
      <Layout style={{ height: "100vh" }}>
        {/* Left Panel */}
        <Content style={{ background: "#fff" }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={leftPanelItems}
            tabBarStyle={{ paddingLeft: "16px", paddingRight: "16px" }}
          />
        </Content>

        {/* Right Panel - Document Viewer */}
        <Sider
          width="45%"
          style={{ background: "#fff", borderLeft: "1px solid #f0f0f0" }}
        >
          <DocumentManager
            projectId={projectId}
            document={selectedDocument}
            highlights={extractedData?.highlights || []}
          />
        </Sider>
      </Layout>

      {/* Modals */}
      <SavePromptModal
        visible={saveModalVisible}
        onClose={() => setSaveModalVisible(false)}
        projectId={projectId}
        promptText={promptText}
        baseVersion={latestPrompt?.version || 0}
        onSuccess={() => {
          setHasUnsavedChanges(false);
          fetchProjectData();
        }}
      />

      <PromptHistoryModal
        visible={historyModalVisible}
        onClose={() => setHistoryModalVisible(false)}
        projectId={projectId}
        currentVersion={latestPrompt?.version || 1}
        hasUnsavedChanges={hasUnsavedChanges}
        onLoadVersion={(version) => {
          // TODO: Load specific version
          message.info(`Loading version ${version}...`);
        }}
        onCompare={(_version) => {
          setCompareModalVisible(true);
        }}
      />

      <ComparePromptsModal
        visible={compareModalVisible}
        onClose={() => setCompareModalVisible(false)}
        projectId={projectId}
        currentVersion={latestPrompt?.version || 1}
      />
    </div>
  );
};

ProjectDetail.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export default ProjectDetail;
