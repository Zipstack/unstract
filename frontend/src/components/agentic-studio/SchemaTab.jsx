import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import {
  Button,
  Space,
  Alert,
  Spin,
  Typography,
  Card,
  Modal,
  Select,
  Empty,
} from "antd";
import {
  ThunderboltOutlined,
  SaveOutlined,
  ReloadOutlined,
  FileSearchOutlined,
  FormatPainterOutlined,
} from "@ant-design/icons";
import MonacoEditor from "@monaco-editor/react";

import {
  schemaApi,
  connectorsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";
import { useSessionStore } from "../../store/session-store";

const { Title, Text } = Typography;

function SchemaTab({ projectId }) {
  const { sessionDetails } = useSessionStore();
  const [schema, setSchema] = useState(null);
  const [schemaContent, setSchemaContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [loadingConnectors, setLoadingConnectors] = useState(false);

  // Generation states
  const [generateModalVisible, setGenerateModalVisible] = useState(false);
  const [generationType, setGenerationType] = useState("regular"); // 'regular' or 'lazy'
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadSchema();
      loadConnectors();
    }
  }, [projectId]);

  const loadSchema = async () => {
    try {
      setLoading(true);
      const schemaData = await schemaApi.get(projectId);

      // Backend returns {schema: {...}, version: ..., created_at: ...}
      // Check if we have actual schema content
      if (
        !schemaData ||
        !schemaData.schema ||
        Object.keys(schemaData.schema).length === 0
      ) {
        setSchema(null);
        setSchemaContent("");
        return;
      }

      setSchema(schemaData);
      // Always pretty-print the schema
      let schemaObj = schemaData.schema;
      if (typeof schemaObj === "string") {
        try {
          schemaObj = JSON.parse(schemaObj);
        } catch (e) {
          // If parsing fails, use as-is
          setSchemaContent(schemaObj);
          return;
        }
      }
      setSchemaContent(JSON.stringify(schemaObj, null, 2));
    } catch (error) {
      if (error.response?.status !== 404) {
        showApiError(error, "Failed to load schema");
      }
      setSchema(null);
      setSchemaContent("");
    } finally {
      setLoading(false);
    }
  };

  const loadConnectors = async () => {
    try {
      setLoadingConnectors(true);
      const orgId = sessionDetails?.orgId;
      if (!orgId) {
        console.error("No organization ID available");
        setConnectors([]);
        return;
      }
      const connectorsData = await connectorsApi.list(orgId);
      console.log("Loaded connectors:", connectorsData);
      const llmConnectors = connectorsData.filter(
        (c) => c.adapter_type === "LLM"
      );
      console.log("Filtered LLM connectors:", llmConnectors);
      setConnectors(llmConnectors);
      if (llmConnectors.length > 0 && !selectedConnector) {
        setSelectedConnector(llmConnectors[0].id);
      }
    } catch (error) {
      console.error("Failed to load connectors:", error);
      console.error("Error details:", error.response?.data);
      showApiError(error, "Failed to load connectors");
      // Set empty array on error so UI shows the warning
      setConnectors([]);
    } finally {
      setLoadingConnectors(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      // Validate JSON
      const parsedSchema = JSON.parse(schemaContent);
      await schemaApi.update(projectId, parsedSchema);
      showApiSuccess("Schema saved successfully");
      setIsEditing(false);
      loadSchema();
    } catch (error) {
      if (error instanceof SyntaxError) {
        showApiError({ message: "Invalid JSON format" }, "Invalid JSON");
      } else {
        showApiError(error, "Failed to save schema");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(schemaContent);
      setSchemaContent(JSON.stringify(parsed, null, 2));
      showApiSuccess("Schema formatted successfully");
    } catch (error) {
      showApiError(
        { message: "Invalid JSON format" },
        "Cannot format invalid JSON"
      );
    }
  };

  const handleGenerateSchema = async () => {
    // Reload connectors when opening modal to get latest list
    await loadConnectors();
    setGenerateModalVisible(true);
  };

  const startSchemaGeneration = async () => {
    try {
      setGenerating(true);
      setGenerateModalVisible(false);

      let response;
      if (generationType === "lazy") {
        // Lazy generation is now synchronous - no polling needed
        response = await schemaApi.generateLazy(projectId, {
          connector_id: selectedConnector,
        });
      } else {
        // Regular schema generation is synchronous - no polling needed
        response = await schemaApi.generate(projectId, {
          connector_id: selectedConnector,
        });
      }

      // Both modes are now synchronous, response is immediate
      setGenerating(false);
      showApiSuccess(response.message || "Schema generated successfully!");
      loadSchema();
    } catch (error) {
      setGenerating(false);
      showApiError(error, "Failed to generate schema");
    }
  };

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
          {/* Header Actions */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <Title level={4} style={{ margin: 0 }}>
                JSON Schema
              </Title>
              <Text type="secondary">
                Define the structure of data to be extracted from documents
              </Text>
            </div>
            <Space>
              {!schema && (
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={handleGenerateSchema}
                  disabled={generating}
                >
                  Generate Schema
                </Button>
              )}
              {schema && !isEditing && (
                <>
                  <Button
                    icon={<ThunderboltOutlined />}
                    onClick={handleGenerateSchema}
                    disabled={generating}
                  >
                    Regenerate
                  </Button>
                  <Button
                    icon={<FileSearchOutlined />}
                    onClick={() => setIsEditing(true)}
                  >
                    Edit
                  </Button>
                </>
              )}
              {isEditing && (
                <>
                  <Button
                    icon={<FormatPainterOutlined />}
                    onClick={handleFormat}
                  >
                    Format JSON
                  </Button>
                  <Button
                    onClick={() => {
                      setIsEditing(false);
                      loadSchema();
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
              {schema && (
                <Button
                  icon={<ReloadOutlined />}
                  onClick={loadSchema}
                  disabled={isEditing}
                >
                  Refresh
                </Button>
              )}
            </Space>
          </div>

          {/* Generation Progress */}
          {generating && (
            <Alert
              type="info"
              showIcon
              message="Generating schema... This may take a few moments."
            />
          )}

          {/* Schema Editor or Empty State */}
          {schema || isEditing ? (
            <div style={{ border: "1px solid #d9d9d9", borderRadius: "4px" }}>
              <MonacoEditor
                height="60vh"
                language="json"
                value={schemaContent}
                onChange={(value) => setSchemaContent(value || "")}
                options={{
                  readOnly: !isEditing,
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
                theme="vs-light"
              />
            </div>
          ) : (
            <Empty
              description={
                <Space direction="vertical" size="large">
                  <Text>No schema defined yet</Text>
                  <Text type="secondary">
                    Generate a schema automatically from your documents or
                    create one manually
                  </Text>
                </Space>
              }
            >
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                size="large"
                onClick={handleGenerateSchema}
                disabled={generating}
              >
                Generate Schema
              </Button>
            </Empty>
          )}
        </Space>
      </Card>

      {/* Generation Modal */}
      <Modal
        title="Generate Schema"
        open={generateModalVisible}
        onCancel={() => setGenerateModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setGenerateModalVisible(false)}>
            Cancel
          </Button>,
          <Button
            key="generate"
            type="primary"
            onClick={startSchemaGeneration}
            disabled={!selectedConnector}
          >
            Generate
          </Button>,
        ]}
      >
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            message="Schema generation will analyze your documents and create a JSON schema"
            description={
              generationType === "lazy"
                ? "Lazy mode will automatically process documents if needed"
                : "Requires documents with summaries to be available"
            }
          />

          <div>
            <Text strong>Generation Type:</Text>
            <Select
              value={generationType}
              onChange={setGenerationType}
              style={{ width: "100%", marginTop: "8px" }}
              options={[
                {
                  label: "Regular - Requires processed documents",
                  value: "regular",
                },
                {
                  label: "Lazy - Auto-process documents if needed",
                  value: "lazy",
                },
              ]}
            />
          </div>

          {connectors.length > 0 && (
            <div>
              <Text strong>LLM Connector:</Text>
              <Select
                value={selectedConnector}
                onChange={setSelectedConnector}
                style={{ width: "100%", marginTop: "8px" }}
                options={connectors.map((c) => ({
                  label: `${c.adapter_name} (${c.adapter_id || "N/A"})`,
                  value: c.id,
                }))}
              />
            </div>
          )}

          {loadingConnectors && (
            <Alert
              type="info"
              showIcon
              message="Loading connectors..."
              description="Fetching available LLM connectors"
            />
          )}

          {!loadingConnectors && connectors.length === 0 && (
            <Alert
              type="warning"
              showIcon
              message="No LLM connectors available"
              description="Please create an LLM connector in Settings first"
            />
          )}
        </Space>
      </Modal>
    </div>
  );
}

SchemaTab.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export default SchemaTab;
