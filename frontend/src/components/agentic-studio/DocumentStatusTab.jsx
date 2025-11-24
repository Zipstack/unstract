import { useState, useEffect } from "react";
import {
  Table,
  Tag,
  Button,
  Space,
  Tooltip,
  Progress,
  Modal,
  Typography,
  Alert,
  Spin,
  Popconfirm,
  Row,
  Col,
  Card,
  Empty,
} from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  EyeOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";

import {
  documentsApi,
  processingApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";
import DocumentViewer from "./DocumentViewer";

const { Text } = Typography;

// Status badge component
const StatusBadge = ({ status, progress, error }) => {
  const statusConfig = {
    complete: {
      icon: <CheckCircleOutlined />,
      color: "success",
      text: "Complete",
    },
    processing: {
      icon: <SyncOutlined spin />,
      color: "processing",
      text: "Processing",
    },
    pending: {
      icon: <ClockCircleOutlined />,
      color: "default",
      text: "Pending",
    },
    error: {
      icon: <ExclamationCircleOutlined />,
      color: "error",
      text: "Error",
    },
  };

  const config = statusConfig[status] || statusConfig.pending;

  if (status === "processing" && progress !== undefined) {
    return (
      <Tooltip title={`${Math.round(progress)}% complete`}>
        <Tag icon={config.icon} color={config.color}>
          {Math.round(progress)}%
        </Tag>
      </Tooltip>
    );
  }

  if (status === "error" && error) {
    return (
      <Tooltip title={error}>
        <Tag icon={config.icon} color={config.color}>
          {config.text}
        </Tag>
      </Tooltip>
    );
  }

  return (
    <Tag icon={config.icon} color={config.color}>
      {config.text}
    </Tag>
  );
};

StatusBadge.propTypes = {
  status: PropTypes.string.isRequired,
  progress: PropTypes.number,
  error: PropTypes.string,
};

function DocumentStatusTab({
  projectId,
  documents,
  selectedDocId,
  onSelectDocument,
  onDocumentsChange,
}) {
  const [documentStatuses, setDocumentStatuses] = useState([]);
  const [processingState, setProcessingState] = useState({});
  const [loading, setLoading] = useState(false);
  const [dataModalVisible, setDataModalVisible] = useState(false);
  const [dataModalContent, setDataModalContent] = useState({
    title: "",
    data: "",
  });
  const [dataModalLoading, setDataModalLoading] = useState(false);
  const [processingDocs, setProcessingDocs] = useState(new Set());

  useEffect(() => {
    if (projectId) {
      loadDocumentStatuses();
      loadProcessingState();
    }
  }, [projectId, documents]);

  const loadDocumentStatuses = async () => {
    try {
      setLoading(true);
      const statuses = await documentsApi.getDocumentStatus(projectId);
      setDocumentStatuses(statuses);
    } catch (error) {
      showApiError(error, "Failed to load document statuses");
    } finally {
      setLoading(false);
    }
  };

  const loadProcessingState = async () => {
    try {
      const state = await processingApi.getProcessingState(projectId);
      const stateMap = {};
      state.documents.forEach((doc) => {
        stateMap[doc.document_id] = doc;
      });
      setProcessingState(stateMap);
    } catch (error) {
      console.error("Failed to load processing state:", error);
    }
  };

  const handleProcessStage = async (documentId, stage) => {
    const stageKey = `${documentId}-${stage}`;
    setProcessingDocs((prev) => new Set(prev).add(stageKey));

    try {
      await documentsApi.processStage(projectId, documentId, { stage });
      showApiSuccess(`${stage} processing started`);

      // Refresh statuses after a delay
      setTimeout(() => {
        loadDocumentStatuses();
        loadProcessingState();
      }, 1000);
    } catch (error) {
      showApiError(error, `Failed to start ${stage} processing`);
    } finally {
      setProcessingDocs((prev) => {
        const newSet = new Set(prev);
        newSet.delete(stageKey);
        return newSet;
      });
    }
  };

  const handleDeleteStage = async (documentId, stage) => {
    try {
      const response = await processingApi.deleteDocumentStage(
        projectId,
        documentId,
        stage
      );
      showApiSuccess(response.message || `${stage} deleted successfully`);
      loadDocumentStatuses();
      loadProcessingState();
    } catch (error) {
      showApiError(error, `Failed to delete ${stage}`);
    }
  };

  const handleViewData = async (documentId, stage, title) => {
    setDataModalVisible(true);
    setDataModalContent({ title, data: "" });
    setDataModalLoading(true);

    try {
      let data;
      switch (stage) {
        case "raw_text": {
          const rawTextResp = await documentsApi.getRawText(
            projectId,
            documentId
          );
          data = rawTextResp.raw_text;
          break;
        }
        case "summary": {
          const summaryResp = await documentsApi.getSummary(
            projectId,
            documentId
          );
          data = summaryResp.summary_text;
          break;
        }
        case "verified_data": {
          const verifiedResp = await documentsApi.getVerifiedData(
            projectId,
            documentId
          );
          data = JSON.stringify(verifiedResp.data, null, 2);
          break;
        }
        case "extraction": {
          const extractedResp = await documentsApi.getExtractionData(
            projectId,
            documentId
          );
          data = JSON.stringify(extractedResp.data, null, 2);
          break;
        }
        default:
          data = "No data available";
      }
      setDataModalContent({ title, data });
    } catch (error) {
      setDataModalContent({
        title,
        data: "Failed to load data: " + error.message,
      });
    } finally {
      setDataModalLoading(false);
    }
  };

  const getStageStatus = (documentId, stageName) => {
    // First check documentStatuses (actual data existence)
    // Backend returns document_id, not id
    const docStatus = documentStatuses.find(
      (ds) => ds.document_id === documentId || ds.id === documentId
    );
    if (docStatus) {
      const statusKey = `${stageName}_status`;
      const status = docStatus[statusKey];
      // Backend returns "completed", frontend expects "complete"
      if (status === "complete" || status === "completed") {
        return { status: "complete" };
      }
    }

    // Then check processingState for in-progress tasks
    const docState = processingState[documentId];
    if (docState && docState[stageName]) {
      const stageState = docState[stageName];
      // Only use processing state if it's actually processing
      if (
        stageState.status === "processing" ||
        stageState.status === "in_progress"
      ) {
        return {
          status: "processing",
          progress: stageState.progress,
          error: stageState.error,
        };
      }
      if (stageState.status === "error" || stageState.status === "failed") {
        return {
          status: "error",
          error: stageState.error || stageState.message,
        };
      }
    }

    // Default to pending
    return { status: "pending" };
  };

  const columns = [
    {
      title: "Document",
      dataIndex: "original_filename",
      key: "filename",
      width: 250,
      ellipsis: true,
      fixed: "left",
    },
    {
      title: "Raw Text",
      key: "raw_text",
      width: 150,
      render: (_, record) => {
        const { status, progress, error } = getStageStatus(
          record.id,
          "raw_text"
        );
        const isProcessing = processingDocs.has(`${record.id}-raw_text`);

        return (
          <Space direction="vertical" size="small" style={{ width: "100%" }}>
            <StatusBadge status={status} progress={progress} error={error} />
            <Space size="small">
              {status === "complete" && (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() =>
                    handleViewData(record.id, "raw_text", "Raw Text")
                  }
                >
                  View
                </Button>
              )}
              {status === "pending" && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={isProcessing}
                  onClick={() => handleProcessStage(record.id, "raw_text")}
                >
                  Process
                </Button>
              )}
              {status === "complete" && (
                <Popconfirm
                  title="Delete raw text?"
                  onConfirm={() => handleDeleteStage(record.id, "raw_text")}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              )}
            </Space>
          </Space>
        );
      },
    },
    {
      title: "Summary",
      key: "summary",
      width: 150,
      render: (_, record) => {
        const { status, progress, error } = getStageStatus(
          record.id,
          "summary"
        );
        const isProcessing = processingDocs.has(`${record.id}-summary`);

        return (
          <Space direction="vertical" size="small" style={{ width: "100%" }}>
            <StatusBadge status={status} progress={progress} error={error} />
            <Space size="small">
              {status === "complete" && (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() =>
                    handleViewData(record.id, "summary", "Summary")
                  }
                >
                  View
                </Button>
              )}
              {status === "pending" && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={isProcessing}
                  onClick={() => handleProcessStage(record.id, "summary")}
                >
                  Process
                </Button>
              )}
              {status === "complete" && (
                <Popconfirm
                  title="Delete summary?"
                  onConfirm={() => handleDeleteStage(record.id, "summary")}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              )}
            </Space>
          </Space>
        );
      },
    },
    {
      title: "Verified Data",
      key: "verified_data",
      width: 150,
      render: (_, record) => {
        const { status, progress, error } = getStageStatus(
          record.id,
          "verified_data"
        );
        const isProcessing = processingDocs.has(`${record.id}-verified_data`);

        return (
          <Space direction="vertical" size="small" style={{ width: "100%" }}>
            <StatusBadge status={status} progress={progress} error={error} />
            <Space size="small">
              {status === "complete" && (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() =>
                    handleViewData(record.id, "verified_data", "Verified Data")
                  }
                >
                  View
                </Button>
              )}
              {status === "pending" && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={isProcessing}
                  onClick={() => handleProcessStage(record.id, "verified_data")}
                >
                  Process
                </Button>
              )}
              {status === "complete" && (
                <Popconfirm
                  title="Delete verified data?"
                  onConfirm={() =>
                    handleDeleteStage(record.id, "verified_data")
                  }
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              )}
            </Space>
          </Space>
        );
      },
    },
    {
      title: "Extraction",
      key: "extraction",
      width: 150,
      render: (_, record) => {
        const { status, progress, error } = getStageStatus(
          record.id,
          "extraction"
        );
        const isProcessing = processingDocs.has(`${record.id}-extraction`);

        return (
          <Space direction="vertical" size="small" style={{ width: "100%" }}>
            <StatusBadge status={status} progress={progress} error={error} />
            <Space size="small">
              {status === "complete" && (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() =>
                    handleViewData(record.id, "extraction", "Extracted Data")
                  }
                >
                  View
                </Button>
              )}
              {status === "pending" && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={isProcessing}
                  onClick={() => handleProcessStage(record.id, "extraction")}
                >
                  Extract
                </Button>
              )}
            </Space>
          </Space>
        );
      },
    },
    {
      title: "Accuracy",
      key: "accuracy",
      width: 120,
      render: (_, record) => {
        const docStatus = documentStatuses.find((ds) => ds.id === record.id);
        if (
          !docStatus ||
          docStatus.accuracy === null ||
          docStatus.accuracy === undefined
        ) {
          return <Text type="secondary">N/A</Text>;
        }

        const accuracy = Math.round(docStatus.accuracy);
        let color = "red";
        if (accuracy >= 90) color = "green";
        else if (accuracy >= 70) color = "orange";

        return (
          <Tooltip
            title={`${docStatus.accuracy_matches}/${docStatus.accuracy_total_fields} fields match`}
          >
            <Progress
              percent={accuracy}
              size="small"
              strokeColor={color}
              format={(percent) => `${percent}%`}
            />
          </Tooltip>
        );
      },
    },
  ];

  const selectedDocument = documents.find((doc) => doc.id === selectedDocId);

  return (
    <Row gutter={16} style={{ height: "calc(100vh - 250px)" }}>
      {/* Left Panel - Document List */}
      <Col span={14} style={{ height: "100%", overflow: "auto" }}>
        <Alert
          message="Document Processing Pipeline"
          description="Process documents through each stage: Raw Text → Summary → Verified Data → Extraction"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Table
          columns={columns}
          dataSource={documents}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1000, y: "calc(100vh - 450px)" }}
          size="middle"
          rowSelection={{
            type: "radio",
            selectedRowKeys: selectedDocId ? [selectedDocId] : [],
            onChange: (selectedRowKeys) => {
              if (selectedRowKeys.length > 0) {
                onSelectDocument?.(selectedRowKeys[0]);
              }
            },
          }}
          onRow={(record) => ({
            onClick: () => {
              onSelectDocument?.(record.id);
            },
            style: {
              cursor: "pointer",
              background: record.id === selectedDocId ? "#e6f7ff" : undefined,
            },
          })}
        />
      </Col>

      {/* Right Panel - Document Viewer */}
      <Col span={10} style={{ height: "100%", overflow: "hidden" }}>
        <Card
          style={{ height: "100%", display: "flex", flexDirection: "column" }}
          bodyStyle={{
            flex: 1,
            overflow: "hidden",
            padding: 0,
          }}
        >
          {selectedDocument ? (
            <DocumentViewer
              projectId={projectId}
              document={selectedDocument}
              onDocumentUpdate={() => {
                loadDocumentStatuses();
                onDocumentsChange?.();
              }}
            />
          ) : (
            <Empty
              description="Select a document to view"
              style={{ marginTop: "20%" }}
            />
          )}
        </Card>
      </Col>

      <Modal
        title={dataModalContent.title}
        open={dataModalVisible}
        onCancel={() => setDataModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDataModalVisible(false)}>
            Close
          </Button>,
        ]}
        width={800}
      >
        {dataModalLoading ? (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <Spin size="large" />
          </div>
        ) : (
          <pre
            style={{
              maxHeight: "60vh",
              overflow: "auto",
              padding: "16px",
              background: "#f5f5f5",
              borderRadius: "4px",
              fontSize: "12px",
            }}
          >
            {dataModalContent.data}
          </pre>
        )}
      </Modal>
    </Row>
  );
}

DocumentStatusTab.propTypes = {
  projectId: PropTypes.string.isRequired,
  documents: PropTypes.array.isRequired,
  selectedDocId: PropTypes.string,
  onSelectDocument: PropTypes.func,
  onDocumentsChange: PropTypes.func,
};

export default DocumentStatusTab;
