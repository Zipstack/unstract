import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Layout, Tabs, Button, Space, Typography, Spin, Divider } from "antd";
import {
  CodeOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  TableOutlined,
  SettingOutlined,
  ArrowLeftOutlined,
  FolderOpenOutlined,
} from "@ant-design/icons";

import {
  projectsApi,
  documentsApi,
  showApiError,
} from "../../helpers/agentic-api";
import DocumentStatusTab from "../../components/agentic-studio/DocumentStatusTab";
import SchemaTab from "../../components/agentic-studio/SchemaTab";
import PromptTab from "../../components/agentic-studio/PromptTab";
import VerifiedDataTab from "../../components/agentic-studio/VerifiedDataTab";
import ExtractedDataTab from "../../components/agentic-studio/ExtractedDataTab";
import AnalyticsTab from "../../components/agentic-studio/AnalyticsTab";
import MatrixTab from "../../components/agentic-studio/MatrixTab";
import ProjectSettingsTab from "../../components/agentic-studio/ProjectSettingsTab";
import DocumentManager from "../../components/agentic-studio/DocumentManager";

const { Content, Header } = Layout;
const { Title, Text } = Typography;

function AgenticStudioProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("status");
  const [showDocumentManager, setShowDocumentManager] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState(null);

  useEffect(() => {
    // Initialize tab from URL hash
    const hash = window.location.hash.slice(1);
    const validTabs = [
      "status",
      "schema",
      "prompt",
      "verified",
      "extracted",
      "analytics",
      "matrix",
      "settings",
    ];
    if (validTabs.includes(hash)) {
      setActiveTab(hash);
    }

    loadProjectData();
  }, [id]);

  useEffect(() => {
    // Update URL hash when tab changes
    window.location.hash = activeTab;
  }, [activeTab]);

  const loadProjectData = async () => {
    try {
      setLoading(true);
      // Load project data first to unblock page render
      const projectData = await projectsApi.get(id);
      setProject(projectData);
      setLoading(false);

      // Load documents asynchronously after page is rendered
      loadDocuments();
    } catch (error) {
      showApiError(error, "Failed to load project");
      setLoading(false);
    }
  };

  const loadDocuments = async () => {
    try {
      const documentsData = await documentsApi.list(id);
      setDocuments(documentsData);

      // Select first document by default if available
      if (documentsData.length > 0 && !selectedDocId) {
        setSelectedDocId(documentsData[0].id);
      }
    } catch (error) {
      showApiError(error, "Failed to load documents");
    }
  };

  const handleDocumentsUpdated = () => {
    loadProjectData();
  };

  const tabItems = [
    {
      key: "status",
      label: (
        <span>
          <CheckCircleOutlined /> Status
        </span>
      ),
      children: project && (
        <DocumentStatusTab
          projectId={id}
          project={project}
          documents={documents}
          selectedDocId={selectedDocId}
          onSelectDocument={setSelectedDocId}
          onDocumentsChange={handleDocumentsUpdated}
        />
      ),
    },
    {
      key: "schema",
      label: (
        <span>
          <DatabaseOutlined /> Schema
        </span>
      ),
      children: project && <SchemaTab projectId={id} project={project} />,
    },
    {
      key: "prompt",
      label: (
        <span>
          <CodeOutlined /> Prompt
        </span>
      ),
      children: project && <PromptTab projectId={id} project={project} />,
    },
    {
      key: "verified",
      label: (
        <span>
          <CheckCircleOutlined /> Verified Data
        </span>
      ),
      children: project && (
        <VerifiedDataTab
          projectId={id}
          project={project}
          documents={documents}
          selectedDocId={selectedDocId}
          onSelectDocument={setSelectedDocId}
        />
      ),
    },
    {
      key: "extracted",
      label: (
        <span>
          <ThunderboltOutlined /> Extracted Data
        </span>
      ),
      children: project && (
        <ExtractedDataTab
          projectId={id}
          project={project}
          documents={documents}
          selectedDocId={selectedDocId}
          onSelectDocument={setSelectedDocId}
        />
      ),
    },
    {
      key: "analytics",
      label: (
        <span>
          <BarChartOutlined /> Analytics
        </span>
      ),
      children: project && <AnalyticsTab projectId={id} project={project} />,
    },
    {
      key: "matrix",
      label: (
        <span>
          <TableOutlined /> Matrix
        </span>
      ),
      children: project && (
        <MatrixTab projectId={id} project={project} documents={documents} />
      ),
    },
    {
      key: "settings",
      label: (
        <span>
          <SettingOutlined /> Settings
        </span>
      ),
      children: project ? (
        <ProjectSettingsTab project={project} onUpdate={loadProjectData} />
      ) : null,
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "100px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: "100vh", background: "#f0f2f5" }}>
      <Header
        style={{
          background: "#fff",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid #f0f0f0",
        }}
      >
        <Space size="large">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
            size="large"
          >
            Back
          </Button>
          <Divider type="vertical" style={{ height: "32px" }} />
          <Space direction="vertical" size={0}>
            <Title level={4} style={{ margin: 0 }}>
              {project?.name || "Project"}
            </Title>
            {project?.description && (
              <Text type="secondary" style={{ fontSize: "12px" }}>
                {project.description}
              </Text>
            )}
          </Space>
        </Space>

        <Button
          type="primary"
          icon={<FolderOpenOutlined />}
          size="large"
          onClick={() => setShowDocumentManager(true)}
        >
          Manage Documents
        </Button>
      </Header>

      <Content
        style={{
          padding: "24px",
          height: "calc(100vh - 100px)",
          overflow: "auto",
        }}
      >
        <div
          style={{
            background: "#fff",
            borderRadius: "8px",
            padding: "24px",
          }}
        >
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            size="large"
            tabBarStyle={{ marginBottom: "24px" }}
          />
        </div>
      </Content>

      {showDocumentManager && (
        <DocumentManager
          projectId={id}
          documents={documents}
          onClose={() => setShowDocumentManager(false)}
          onDocumentsChange={handleDocumentsUpdated}
        />
      )}
    </Layout>
  );
}

export default AgenticStudioProjectDetail;
