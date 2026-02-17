import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import { Button, Tag, Typography, Progress, Modal } from "antd";
import {
  UploadOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  SyncOutlined,
  FileTextOutlined,
  InboxOutlined,
  CalendarOutlined,
  FileOutlined,
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

  const getExtractionStatusTag = (status, record) => {
    const displayText = record.extraction_status_display || status;
    switch (status) {
      case "complete":
        return (
          <>
            <CheckCircleOutlined
              className="ref-card-icon"
              style={{ color: "#52c41a" }}
            />
            <Tag color="green">{displayText}</Tag>
          </>
        );
      case "failed":
        return (
          <>
            <CloseCircleOutlined
              className="ref-card-icon"
              style={{ color: "#f5222d" }}
            />
            <Tag color="red">{displayText}</Tag>
          </>
        );
      case "processing":
        return (
          <>
            <LoadingOutlined
              className="ref-card-icon"
              style={{ color: "#1890ff" }}
            />
            <Tag color="blue">{displayText}</Tag>
          </>
        );
      case "pending":
        return (
          <>
            <SyncOutlined
              className="ref-card-icon"
              style={{ color: "#faad14" }}
            />
            <Tag color="orange">{displayText}</Tag>
          </>
        );
      default:
        return <Text>{displayText}</Text>;
    }
  };

  return (
    <div className="reference-data-tab">
      <div className="ref-tab-header">
        <div>
          <Title level={4} className="ref-tab-title">
            Reference Data
          </Title>
          <Text type="secondary">
            Upload and manage reference data files for enrichment
          </Text>
        </div>
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
      </div>

      <div className="ref-cards-container">
        {loading ? (
          <div className="ref-loading">Loading...</div>
        ) : dataSources.length === 0 ? (
          <div className="ref-empty">
            <Text type="secondary">
              No reference data yet. Upload a file to get started.
            </Text>
          </div>
        ) : (
          dataSources.map((ds) => (
            <div key={ds.id} className="ref-data-card">
              <div className="ref-card-header">
                <Text className="ref-card-filename">{ds.file_name}</Text>
                <Button
                  type="text"
                  icon={<DeleteOutlined />}
                  className="ref-card-delete"
                  onClick={() => handleDelete(ds.id)}
                />
              </div>

              <div className="ref-card-body">
                <div className="ref-card-row">
                  <Text className="ref-card-label">VERSION</Text>
                  <div className="ref-card-value">
                    <FileTextOutlined className="ref-card-icon" />
                    <Tag>{`V${ds.version_number}`}</Tag>
                    {ds.is_latest && <Tag color="blue">Latest</Tag>}
                  </div>
                </div>

                <div className="ref-card-row">
                  <Text className="ref-card-label">EXTRACTION STATUS</Text>
                  <div className="ref-card-value">
                    {getExtractionStatusTag(ds.extraction_status, ds)}
                  </div>
                </div>

                <div className="ref-card-row">
                  <Text className="ref-card-label">SIZE</Text>
                  <div className="ref-card-value">
                    <FileOutlined className="ref-card-icon" />
                    <Text>
                      {ds.file_size
                        ? `${(ds.file_size / 1024 / 1024).toFixed(2)} MB`
                        : "-"}
                    </Text>
                  </div>
                </div>

                <div className="ref-card-row">
                  <Text className="ref-card-label">UPLOADED</Text>
                  <div className="ref-card-value">
                    <CalendarOutlined className="ref-card-icon" />
                    <Text>{new Date(ds.created_at).toLocaleString()}</Text>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

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
