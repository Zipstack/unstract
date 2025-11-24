import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import {
  Button,
  Space,
  Alert,
  Spin,
  Typography,
  Card,
  Select,
  Empty,
  message,
  Modal,
  Table,
  Tag,
} from "antd";
import {
  SaveOutlined,
  ReloadOutlined,
  EditOutlined,
  FileTextOutlined,
  FormatPainterOutlined,
  TableOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import MonacoEditor from "@monaco-editor/react";

import {
  extractionApi,
  schemaApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";

const { Title, Text } = Typography;

function VerifiedDataTab({
  projectId,
  documents,
  selectedDocId,
  onSelectDocument,
}) {
  const [verifiedData, setVerifiedData] = useState(null);
  const [verifiedDataContent, setVerifiedDataContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [schema, setSchema] = useState(null);
  const [allVerifiedDataVisible, setAllVerifiedDataVisible] = useState(false);
  const [allVerifiedData, setAllVerifiedData] = useState([]);
  const [loadingAllData, setLoadingAllData] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadSchema();
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId && selectedDocId) {
      loadVerifiedData();
    }
  }, [projectId, selectedDocId]);

  const loadSchema = async () => {
    try {
      const schemaData = await schemaApi.get(projectId);
      setSchema(schemaData);
    } catch (error) {
      // Schema might not exist yet, that's okay
      setSchema(null);
    }
  };

  const loadVerifiedData = async () => {
    try {
      setLoading(true);
      const data = await extractionApi.getVerifiedData(
        projectId,
        selectedDocId
      );
      setVerifiedData(data);
      setVerifiedDataContent(JSON.stringify(data.data || {}, null, 2));
    } catch (error) {
      if (error.response?.status !== 404) {
        showApiError(error, "Failed to load verified data");
      }
      setVerifiedData(null);
      setVerifiedDataContent("{}");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      // Validate JSON
      const parsedData = JSON.parse(verifiedDataContent);

      // Optional: Validate against schema if available
      if (schema) {
        // Basic validation - can be enhanced with ajv or similar
        const schemaObj =
          typeof schema.json_schema === "string"
            ? JSON.parse(schema.json_schema)
            : schema.json_schema;

        // Check if all required fields from schema are present
        if (schemaObj.required) {
          const missingFields = schemaObj.required.filter(
            (field) => !(field in parsedData)
          );
          if (missingFields.length > 0) {
            message.warning(
              `Missing required fields: ${missingFields.join(", ")}`
            );
          }
        }
      }

      await extractionApi.saveVerifiedData(
        projectId,
        selectedDocId,
        parsedData
      );
      showApiSuccess("Verified data saved successfully");
      setIsEditing(false);
      loadVerifiedData();
    } catch (error) {
      if (error instanceof SyntaxError) {
        showApiError({ message: "Invalid JSON format" }, "Invalid JSON");
      } else {
        showApiError(error, "Failed to save verified data");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(verifiedDataContent);
      setVerifiedDataContent(JSON.stringify(parsed, null, 2));
      showApiSuccess("JSON formatted successfully");
    } catch (error) {
      showApiError(
        { message: "Invalid JSON format" },
        "Cannot format invalid JSON"
      );
    }
  };

  const handleGenerateVerifiedData = async () => {
    try {
      setGenerating(true);
      message.loading({
        content: "Generating verified data using LLM...",
        key: "generate",
        duration: 0,
      });

      const result = await extractionApi.generateVerifiedData(
        projectId,
        selectedDocId
      );

      message.success({
        content: "Verified data generated successfully!",
        key: "generate",
      });

      // Load the newly generated data
      setVerifiedData(result);
      setVerifiedDataContent(JSON.stringify(result.data || {}, null, 2));
      setIsEditing(true); // Allow user to review and edit
      showApiSuccess("Verified data generated - please review and save");
    } catch (error) {
      message.error({
        content: "Failed to generate verified data",
        key: "generate",
      });
      showApiError(error, "Failed to generate verified data");
    } finally {
      setGenerating(false);
    }
  };

  const loadAllVerifiedData = async () => {
    try {
      setLoadingAllData(true);
      const allData = await extractionApi.getAllVerifiedData(projectId);
      setAllVerifiedData(allData);
      setAllVerifiedDataVisible(true);
    } catch (error) {
      showApiError(error, "Failed to load all verified data");
    } finally {
      setLoadingAllData(false);
    }
  };

  const selectedDocument = documents.find((d) => d.id === selectedDocId);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          {/* Header with Document Selector */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              flexWrap: "wrap",
              gap: "16px",
            }}
          >
            <div style={{ minWidth: "200px" }}>
              <Title level={4} style={{ margin: 0, marginBottom: "8px" }}>
                Verified Data
              </Title>
              <Text type="secondary">
                Ground truth data for training and comparison
              </Text>
            </div>
            <Space size="middle" wrap>
              <div>
                <Text strong style={{ marginRight: "8px" }}>
                  Document:
                </Text>
                <Select
                  value={selectedDocId}
                  onChange={onSelectDocument}
                  style={{ width: 200 }}
                  placeholder="Select a document"
                  options={documents.map((doc) => ({
                    label: doc.original_filename,
                    value: doc.id,
                  }))}
                />
              </div>
              <Space wrap>
                <Button
                  icon={<TableOutlined />}
                  onClick={loadAllVerifiedData}
                  loading={loadingAllData}
                >
                  View All
                </Button>
                {selectedDocId && (
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={loadVerifiedData}
                    loading={loading}
                  >
                    Refresh
                  </Button>
                )}
                {verifiedData && !isEditing && (
                  <Button
                    icon={<EditOutlined />}
                    onClick={() => setIsEditing(true)}
                  >
                    Edit
                  </Button>
                )}
                {isEditing && (
                  <>
                    <Button
                      icon={<FormatPainterOutlined />}
                      onClick={handleFormat}
                    >
                      Format
                    </Button>
                    <Button
                      onClick={() => {
                        setIsEditing(false);
                        loadVerifiedData();
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      onClick={handleSave}
                      loading={saving}
                    >
                      Save
                    </Button>
                  </>
                )}
                {!verifiedData && selectedDocId && (
                  <>
                    <Button
                      type="primary"
                      icon={<ThunderboltOutlined />}
                      onClick={handleGenerateVerifiedData}
                      loading={generating}
                    >
                      Generate with LLM
                    </Button>
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => setIsEditing(true)}
                    >
                      Create Manually
                    </Button>
                  </>
                )}
              </Space>
            </Space>
          </div>

          {/* Info Alert */}
          {!verifiedData && !isEditing && (
            <Alert
              type="info"
              showIcon
              message="No verified data for this document yet"
              description="Create verified data to establish ground truth for extraction comparison and accuracy calculation."
            />
          )}

          {schema && (
            <Alert
              type="success"
              showIcon
              icon={<FileTextOutlined />}
              message="Schema available for reference"
              description="The JSON structure should match the project schema for consistency."
              style={{ marginBottom: 0 }}
            />
          )}

          {/* Editor or Empty State */}
          {verifiedData || isEditing ? (
            <div style={{ border: "1px solid #d9d9d9", borderRadius: "4px" }}>
              <MonacoEditor
                height="60vh"
                language="json"
                value={verifiedDataContent}
                onChange={(value) => setVerifiedDataContent(value || "")}
                options={{
                  readOnly: !isEditing,
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  formatOnPaste: true,
                  formatOnType: true,
                }}
                theme="vs-light"
              />
            </div>
          ) : (
            <Empty
              description={
                <Space direction="vertical" size="large">
                  <Text>No verified data for selected document</Text>
                  <Text type="secondary">
                    {selectedDocument
                      ? `Create verified data for "${selectedDocument.original_filename}"`
                      : "Select a document to view or create verified data"}
                  </Text>
                </Space>
              }
            >
              {selectedDocument && (
                <Space size="large">
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    size="large"
                    onClick={handleGenerateVerifiedData}
                    loading={generating}
                  >
                    Generate with LLM
                  </Button>
                  <Button
                    icon={<EditOutlined />}
                    size="large"
                    onClick={() => setIsEditing(true)}
                  >
                    Create Manually
                  </Button>
                </Space>
              )}
            </Empty>
          )}

          {/* Document Info */}
          {selectedDocument && (verifiedData || isEditing) && (
            <Card size="small" type="inner" title="Document Information">
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <div>
                  <Text strong>Filename: </Text>
                  <Text>{selectedDocument.original_filename}</Text>
                </div>
                <div>
                  <Text strong>Uploaded: </Text>
                  <Text>
                    {new Date(selectedDocument.uploaded_at).toLocaleString()}
                  </Text>
                </div>
                {selectedDocument.pages && (
                  <div>
                    <Text strong>Pages: </Text>
                    <Text>{selectedDocument.pages}</Text>
                  </div>
                )}
                {verifiedData && (
                  <div>
                    <Text strong>Last Updated: </Text>
                    <Text>
                      {new Date(
                        verifiedData.updated_at || verifiedData.created_at
                      ).toLocaleString()}
                    </Text>
                  </div>
                )}
              </Space>
            </Card>
          )}
        </Space>
      </Card>

      {/* All Verified Data Modal */}
      <Modal
        title="All Verified Data Summary"
        open={allVerifiedDataVisible}
        onCancel={() => setAllVerifiedDataVisible(false)}
        footer={[
          <Button key="close" onClick={() => setAllVerifiedDataVisible(false)}>
            Close
          </Button>,
        ]}
        width={1000}
      >
        <Table
          dataSource={allVerifiedData}
          rowKey="document_id"
          columns={[
            {
              title: "Document",
              dataIndex: "document_id",
              key: "document_id",
              render: (docId) => {
                const doc = documents.find((d) => d.id === docId);
                return doc ? doc.original_filename : docId;
              },
            },
            {
              title: "Status",
              dataIndex: "data",
              key: "status",
              render: (data) => (
                <Tag
                  color={
                    data && Object.keys(data).length > 0 ? "success" : "default"
                  }
                >
                  {data && Object.keys(data).length > 0 ? "Has Data" : "Empty"}
                </Tag>
              ),
            },
            {
              title: "Fields",
              dataIndex: "data",
              key: "fields",
              render: (data) => (data ? Object.keys(data).length : 0),
            },
            {
              title: "Last Updated",
              dataIndex: "updated_at",
              key: "updated_at",
              render: (date) =>
                date ? new Date(date).toLocaleString() : "N/A",
            },
            {
              title: "Actions",
              key: "actions",
              render: (_, record) => (
                <Button
                  size="small"
                  onClick={() => {
                    onSelectDocument(record.document_id);
                    setAllVerifiedDataVisible(false);
                  }}
                >
                  View
                </Button>
              ),
            },
          ]}
          pagination={{ pageSize: 10 }}
          loading={loadingAllData}
        />
      </Modal>
    </div>
  );
}

VerifiedDataTab.propTypes = {
  projectId: PropTypes.string.isRequired,
  documents: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      original_filename: PropTypes.string,
      uploaded_at: PropTypes.string,
      pages: PropTypes.number,
    })
  ).isRequired,
  selectedDocId: PropTypes.string,
  onSelectDocument: PropTypes.func.isRequired,
};

export default VerifiedDataTab;
