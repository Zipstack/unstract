import { useState } from "react";
import {
  Modal,
  Upload,
  List,
  Button,
  Space,
  Typography,
  Popconfirm,
  message,
  Tag,
} from "antd";
import {
  InboxOutlined,
  DeleteOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";

import {
  documentsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";

const { Dragger } = Upload;
const { Text } = Typography;

function DocumentManager({ projectId, documents, onClose, onDocumentsChange }) {
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(null);

  const uploadProps = {
    name: "file",
    multiple: true,
    accept: ".pdf",
    beforeUpload: (file) => {
      // Validate file type
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        message.error(`${file.name} is not a PDF file`);
        return Upload.LIST_IGNORE;
      }
      return false; // Prevent auto upload
    },
    onChange: async (info) => {
      const { fileList } = info;

      if (fileList.length > 0 && !uploading) {
        setUploading(true);

        try {
          // Upload all files
          const uploadPromises = fileList
            .filter((file) => file.originFileObj)
            .map((file) => documentsApi.upload(projectId, file.originFileObj));

          await Promise.all(uploadPromises);
          showApiSuccess(
            `${fileList.length} document(s) uploaded successfully`
          );

          // Clear the file list
          info.fileList.length = 0;

          // Refresh documents
          if (onDocumentsChange) {
            onDocumentsChange();
          }
        } catch (error) {
          showApiError(error, "Failed to upload documents");
        } finally {
          setUploading(false);
        }
      }
    },
    showUploadList: false,
  };

  const handleDelete = async (documentId, filename) => {
    try {
      setDeleting(documentId);
      await documentsApi.delete(projectId, documentId);
      showApiSuccess(`Document "${filename}" deleted successfully`);

      if (onDocumentsChange) {
        onDocumentsChange();
      }
    } catch (error) {
      showApiError(error, "Failed to delete document");
    } finally {
      setDeleting(null);
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(((bytes / Math.pow(k, i)) * 100) / 100) + " " + sizes[i];
  };

  return (
    <Modal
      title="Manage Documents"
      open={true}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          Close
        </Button>,
      ]}
      width={800}
      bodyStyle={{ maxHeight: "70vh", overflowY: "auto" }}
    >
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {/* Upload Section */}
        <div>
          <Text strong style={{ display: "block", marginBottom: "12px" }}>
            Upload Documents
          </Text>
          <Dragger {...uploadProps} disabled={uploading}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              Click or drag PDF files to this area to upload
            </p>
            <p className="ant-upload-hint">
              Support for single or bulk upload. Only PDF files are accepted.
            </p>
          </Dragger>
        </div>

        {/* Documents List */}
        <div>
          <Text strong style={{ display: "block", marginBottom: "12px" }}>
            Documents ({documents.length})
          </Text>

          {documents.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "#8c8c8c",
              }}
            >
              <FileTextOutlined
                style={{ fontSize: "48px", marginBottom: "16px" }}
              />
              <div>No documents uploaded yet</div>
            </div>
          ) : (
            <List
              dataSource={documents}
              rowKey="id"
              renderItem={(doc) => (
                <List.Item
                  actions={[
                    <Popconfirm
                      key="delete"
                      title="Delete Document"
                      description={`Are you sure you want to delete "${doc.original_filename}"?`}
                      onConfirm={() =>
                        handleDelete(doc.id, doc.original_filename)
                      }
                      okText="Yes"
                      cancelText="No"
                    >
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        loading={deleting === doc.id}
                      >
                        Delete
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={<FileTextOutlined style={{ fontSize: "24px" }} />}
                    title={
                      <Space>
                        {doc.original_filename}
                        {doc.raw_text && (
                          <Tag color="success" icon={<CheckCircleOutlined />}>
                            Processed
                          </Tag>
                        )}
                      </Space>
                    }
                    description={
                      <Space split="|">
                        <Text type="secondary" style={{ fontSize: "12px" }}>
                          Uploaded: {formatDate(doc.uploaded_at)}
                        </Text>
                        {doc.size_bytes && (
                          <Text type="secondary" style={{ fontSize: "12px" }}>
                            Size: {formatFileSize(doc.size_bytes)}
                          </Text>
                        )}
                        {doc.pages && (
                          <Text type="secondary" style={{ fontSize: "12px" }}>
                            Pages: {doc.pages}
                          </Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
              bordered
              style={{ background: "#fafafa" }}
            />
          )}
        </div>
      </Space>
    </Modal>
  );
}

DocumentManager.propTypes = {
  projectId: PropTypes.string.isRequired,
  documents: PropTypes.array.isRequired,
  onClose: PropTypes.func.isRequired,
  onDocumentsChange: PropTypes.func,
};

export default DocumentManager;
