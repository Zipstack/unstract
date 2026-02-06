import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import {
  Table,
  Button,
  Space,
  Tag,
  Typography,
  Progress,
  Modal,
  Tooltip,
} from "antd";
import {
  UploadOutlined,
  FileTextOutlined,
  DeleteOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  DatabaseOutlined,
  InboxOutlined,
} from "@ant-design/icons";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./ReferenceDataTab.css";

const { Title, Text } = Typography;

export function ReferenceDataTab({ project, onUpdate }) {
  const [dataSources, setDataSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchDataSources();
  }, [project.id]);

  const fetchDataSources = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/data_sources/`
      );
      setDataSources(response.data || []);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to fetch data sources",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file) => {
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("extract_text", "true");
    formData.append("metadata", JSON.stringify({ source: "manual_upload" }));

    try {
      await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/upload_reference_data/`,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        }
      );

      setAlertDetails({
        type: "success",
        content: "Reference data uploaded successfully",
      });
      setUploadModalOpen(false);
      fetchDataSources();
      onUpdate();
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to upload file",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleFileInputChange = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      handleUpload(file);
    }
    // Reset input so same file can be selected again
    event.target.value = "";
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!uploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    if (uploading) return;

    const file = event.dataTransfer?.files?.[0];
    if (file) {
      handleUpload(file);
    }
  };

  const handleDelete = async (dataSourceId) => {
    Modal.confirm({
      title: "Delete Reference Data",
      content: "Are you sure you want to delete this reference data?",
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        try {
          await axiosPrivate.delete(
            `/api/v1/unstract/${sessionDetails?.orgId}/lookup/data-sources/${dataSourceId}/`,
            {
              headers: {
                "X-CSRFToken": sessionDetails?.csrfToken,
              },
            }
          );
          setAlertDetails({
            type: "success",
            content: "Reference data deleted successfully",
          });
          fetchDataSources();
          onUpdate();
        } catch (error) {
          setAlertDetails({
            type: "error",
            content: "Failed to delete reference data",
          });
        }
      },
    });
  };

  const handleIndexAll = async () => {
    Modal.confirm({
      title: "Index All Reference Data",
      content:
        "This will index all completed reference data using the default profile. Continue?",
      okText: "Index All",
      okType: "primary",
      onOk: async () => {
        setIndexing(true);
        try {
          const response = await axiosPrivate.post(
            `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/index_all/`,
            {},
            {
              headers: {
                "X-CSRFToken": sessionDetails?.csrfToken,
              },
            }
          );

          const results = response.data?.results || {};
          setAlertDetails({
            type: "success",
            content: `Indexing completed: ${results.success || 0} successful, ${
              results.failed || 0
            } failed`,
          });

          fetchDataSources();
          onUpdate();
        } catch (error) {
          setAlertDetails({
            type: "error",
            content:
              error.response?.data?.error || "Failed to index reference data",
          });
        } finally {
          setIndexing(false);
        }
      },
    });
  };

  const getExtractionStatusIcon = (status) => {
    switch (status) {
      case "complete":
        return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
      case "failed":
        return <CloseCircleOutlined style={{ color: "#f5222d" }} />;
      case "processing":
        return <LoadingOutlined style={{ color: "#1890ff" }} />;
      case "pending":
        return <SyncOutlined style={{ color: "#faad14" }} />;
      default:
        return null;
    }
  };

  const columns = [
    {
      title: "File",
      dataIndex: "file_name",
      key: "file_name",
      render: (fileName) => (
        <Space>
          <FileTextOutlined />
          <Text>{fileName}</Text>
        </Space>
      ),
    },
    {
      title: "Version",
      dataIndex: "version_number",
      key: "version_number",
      render: (version, record) => (
        <Space>
          <Tag color={record.is_latest ? "green" : "default"}>v{version}</Tag>
          {record.is_latest && <Tag color="blue">Latest</Tag>}
        </Space>
      ),
    },
    {
      title: "Extraction Status",
      dataIndex: "extraction_status",
      key: "extraction_status",
      render: (status, record) => (
        <Space>
          {getExtractionStatusIcon(status)}
          <Text>{record.extraction_status_display || status}</Text>
        </Space>
      ),
    },
    {
      title: "Size",
      dataIndex: "file_size",
      key: "file_size",
      render: (size) => {
        if (!size) return "-";
        const sizeInMB = (size / 1024 / 1024).toFixed(2);
        return `${sizeInMB} MB`;
      },
    },
    {
      title: "Uploaded",
      dataIndex: "created_at",
      key: "created_at",
      render: (date) => new Date(date).toLocaleString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Tooltip title="Delete">
            <Button
              icon={<DeleteOutlined />}
              danger
              size="small"
              onClick={() => handleDelete(record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="reference-data-tab">
      <div className="tab-header">
        <div>
          <Title level={4}>Reference Data</Title>
          <Text type="secondary">
            Upload and manage reference data files for enrichment
          </Text>
        </div>
        <Space>
          <Button
            type="default"
            icon={<DatabaseOutlined />}
            onClick={handleIndexAll}
            loading={indexing}
            disabled={indexing || dataSources.length === 0}
          >
            Index All
          </Button>
          <Button
            type="primary"
            icon={<UploadOutlined />}
            onClick={() => {
              setUploading(false);
              setIsDragging(false);
              setUploadModalOpen(true);
            }}
          >
            Upload Data
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={dataSources}
        loading={loading}
        rowKey="id"
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
        }}
      />

      <Modal
        title="Upload Reference Data"
        open={uploadModalOpen}
        onCancel={() => {
          setUploadModalOpen(false);
          setUploading(false);
          setIsDragging(false);
        }}
        footer={null}
        width={600}
        destroyOnClose
      >
        <input
          type="file"
          id="reference-data-file-input"
          onChange={handleFileInputChange}
          accept=".csv,.json,.txt,.pdf,.xlsx,.xls,.docx,.doc"
          style={{ display: "none" }}
          disabled={uploading}
        />
        <label
          htmlFor="reference-data-file-input"
          className={`upload-dragger ${isDragging ? "dragging" : ""} ${
            uploading ? "disabled" : ""
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{ display: "block" }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            Click or drag file to this area to upload
          </p>
          <p className="ant-upload-hint">
            Support for CSV, JSON, TXT, PDF, Excel, and Word documents. Files
            will be processed for text extraction automatically.
          </p>
        </label>
        {uploading && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={50} status="active" />
            <Text>Uploading and processing file...</Text>
          </div>
        )}
      </Modal>
    </div>
  );
}

ReferenceDataTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};
