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
  Badge,
  List,
  Tag,
  Drawer,
  Form,
  Input,
} from "antd";
import {
  ThunderboltOutlined,
  SaveOutlined,
  ReloadOutlined,
  EditOutlined,
  HistoryOutlined,
  RocketOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";
import MonacoEditor from "@monaco-editor/react";

import {
  promptsApi,
  connectorsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";
import { useSessionStore } from "../../store/session-store";

const { Title, Text } = Typography;
const { TextArea } = Input;

function PromptTab({ projectId }) {
  const { sessionDetails } = useSessionStore();
  const [latestPrompt, setLatestPrompt] = useState(null);
  const [promptContent, setPromptContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [loadingConnectors, setLoadingConnectors] = useState(false);

  // Generation states
  const [generateModalVisible, setGenerateModalVisible] = useState(false);
  const [generationType, setGenerationType] = useState("regular"); // 'regular' or 'with_deps'
  const [generating, setGenerating] = useState(false);

  // History states
  const [historyVisible, setHistoryVisible] = useState(false);
  const [promptHistory, setPromptHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Save prompt modal
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [saveForm] = Form.useForm();

  // Tuning states
  const [tuneModalVisible, setTuneModalVisible] = useState(false);
  const [tuneFieldPath, setTuneFieldPath] = useState("");
  const [tuneStrategy, setTuneStrategy] = useState("single");
  const [tuning, setTuning] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadLatestPrompt();
      loadConnectors();
    }
  }, [projectId]);

  const loadLatestPrompt = async () => {
    try {
      setLoading(true);
      const promptData = await promptsApi.getLatest(projectId);
      setLatestPrompt(promptData);
      setPromptContent(promptData.prompt_text);
    } catch (error) {
      if (error.response?.status !== 404) {
        showApiError(error, "Failed to load prompt");
      }
      setLatestPrompt(null);
      setPromptContent("");
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

  const loadPromptHistory = async () => {
    try {
      setLoadingHistory(true);
      const history = await promptsApi.list(projectId);
      setPromptHistory(history);
    } catch (error) {
      showApiError(error, "Failed to load prompt history");
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleGeneratePrompt = async () => {
    // Reload connectors when opening modal to get latest list
    await loadConnectors();
    setGenerateModalVisible(true);
  };

  const startPromptGeneration = async () => {
    try {
      setGenerating(true);
      setGenerateModalVisible(false);

      let response;
      if (generationType === "with_deps") {
        response = await promptsApi.generateWithDependencies(projectId, {
          connector_id: selectedConnector,
        });
      } else {
        response = await promptsApi.generateInitial(projectId, {
          connector_id: selectedConnector,
        });
      }

      // Synchronous response - prompt is already generated
      setGenerating(false);
      showApiSuccess(response.message || "Prompt generated successfully!");

      // Reload the latest prompt to display it
      await loadLatestPrompt();
    } catch (error) {
      setGenerating(false);
      showApiError(error, "Failed to start prompt generation");
    }
  };

  const handleSavePrompt = () => {
    if (!latestPrompt) return;
    saveForm.setFieldsValue({
      base_version: latestPrompt.version,
    });
    setSaveModalVisible(true);
  };

  const handleSavePromptSubmit = async (values) => {
    try {
      setSaving(true);
      const response = await promptsApi.create(projectId, {
        prompt_text: promptContent,
        short_desc: values.short_desc,
        long_desc: values.long_desc,
        base_version: values.base_version,
      });
      showApiSuccess(response.message || "Prompt saved successfully");
      setSaveModalVisible(false);
      saveForm.resetFields();
      setIsEditing(false);
      loadLatestPrompt();
    } catch (error) {
      showApiError(error, "Failed to save prompt");
    } finally {
      setSaving(false);
    }
  };

  const handleLoadVersion = async (version) => {
    try {
      const prompt = await promptsApi.getByVersion(projectId, version);
      setPromptContent(prompt.prompt_text);
      setIsEditing(true);
      setHistoryVisible(false);
      showApiSuccess(`Loaded prompt v${version}`);
    } catch (error) {
      showApiError(error, "Failed to load prompt version");
    }
  };

  const handleTunePrompt = () => {
    setTuneModalVisible(true);
  };

  const startTuning = async () => {
    if (!tuneFieldPath) {
      showApiError({ message: "Please enter a field path" }, "Invalid input");
      return;
    }

    try {
      setTuning(true);
      setTuneModalVisible(false);

      // Call tune endpoint - it returns synchronously with status
      const response = await promptsApi.tune(projectId, {
        field_path: tuneFieldPath,
        strategy: tuneStrategy,
        connector_id: selectedConnector,
      });

      // Handle synchronous response
      setTuning(false);

      if (response.status === "completed") {
        showApiSuccess(response.message || "Prompt tuned successfully!");
        // Reload the latest prompt to show the new tuned version
        await loadLatestPrompt();
      } else if (response.status === "failed") {
        showApiError(
          { message: response.explanation || response.message },
          "Prompt tuning failed"
        );
      } else {
        showApiSuccess(response.message || "Prompt tuning completed");
        await loadLatestPrompt();
      }
    } catch (error) {
      setTuning(false);
      showApiError(error, "Failed to tune prompt");
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
    <div style={{ height: "calc(100vh - 240px)", overflow: "auto" }}>
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
                Extraction Prompt
                {latestPrompt && (
                  <Tag color="blue" style={{ marginLeft: "12px" }}>
                    v{latestPrompt.version}
                  </Tag>
                )}
              </Title>
              <Space split="|" size="small">
                <Text type="secondary">
                  Instruct the LLM on how to extract data
                </Text>
                {latestPrompt?.accuracy !== null &&
                  latestPrompt?.accuracy !== undefined && (
                    <Badge
                      status={
                        latestPrompt.accuracy >= 90
                          ? "success"
                          : latestPrompt.accuracy >= 70
                          ? "warning"
                          : "error"
                      }
                      text={`Accuracy: ${Math.round(latestPrompt.accuracy)}%`}
                    />
                  )}
              </Space>
            </div>
            <Space>
              {!latestPrompt && (
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={handleGeneratePrompt}
                  disabled={generating}
                >
                  Generate Prompt
                </Button>
              )}
              {latestPrompt && !isEditing && (
                <>
                  <Button
                    icon={<ThunderboltOutlined />}
                    onClick={handleGeneratePrompt}
                    disabled={generating}
                  >
                    Regenerate
                  </Button>
                  <Button
                    icon={<RocketOutlined />}
                    onClick={handleTunePrompt}
                    disabled={tuning}
                  >
                    Tune
                  </Button>
                  <Button
                    icon={<HistoryOutlined />}
                    onClick={() => {
                      loadPromptHistory();
                      setHistoryVisible(true);
                    }}
                  >
                    History
                  </Button>
                  <Button
                    icon={<EditOutlined />}
                    onClick={() => setIsEditing(true)}
                  >
                    Edit
                  </Button>
                </>
              )}
              {isEditing && (
                <>
                  <Button
                    onClick={() => {
                      setIsEditing(false);
                      loadLatestPrompt();
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    onClick={handleSavePrompt}
                  >
                    Save As New Version
                  </Button>
                </>
              )}
              {latestPrompt && (
                <Button
                  icon={<ReloadOutlined />}
                  onClick={loadLatestPrompt}
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
              message={
                <Space>
                  <Spin />
                  <Text strong>Generating prompt...</Text>
                </Space>
              }
            />
          )}

          {/* Tuning Progress */}
          {tuning && (
            <Alert
              type="info"
              showIcon
              message={
                <Space>
                  <Spin />
                  <Text strong>
                    Tuning prompt for field &quot;{tuneFieldPath}&quot;...
                  </Text>
                </Space>
              }
            />
          )}

          {/* Prompt Editor or Empty State */}
          {latestPrompt || isEditing ? (
            <div style={{ border: "1px solid #d9d9d9", borderRadius: "4px" }}>
              <MonacoEditor
                height="500px"
                language="markdown"
                value={promptContent}
                onChange={(value) => setPromptContent(value || "")}
                options={{
                  readOnly: !isEditing,
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  wordWrap: "on",
                }}
                theme="vs-light"
              />
            </div>
          ) : (
            <Empty
              description={
                <Space direction="vertical" size="large">
                  <Text>No prompt defined yet</Text>
                  <Text type="secondary">
                    Generate a prompt automatically or create one manually
                  </Text>
                </Space>
              }
            >
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                size="large"
                onClick={handleGeneratePrompt}
                disabled={generating}
              >
                Generate Prompt
              </Button>
            </Empty>
          )}

          {/* Prompt Metadata */}
          {latestPrompt && (
            <Card size="small" type="inner" title="Prompt Information">
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <div>
                  <Text strong>Short Description: </Text>
                  <Text>{latestPrompt.short_desc || "N/A"}</Text>
                </div>
                <div>
                  <Text strong>Long Description: </Text>
                  <Text>{latestPrompt.long_desc || "N/A"}</Text>
                </div>
                <div>
                  <Text strong>Created: </Text>
                  <Text>
                    {new Date(latestPrompt.created_at).toLocaleString()}
                  </Text>
                </div>
              </Space>
            </Card>
          )}
        </Space>
      </Card>

      {/* Generation Modal */}
      <Modal
        title="Generate Prompt"
        open={generateModalVisible}
        onCancel={() => setGenerateModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setGenerateModalVisible(false)}>
            Cancel
          </Button>,
          <Button
            key="generate"
            type="primary"
            onClick={startPromptGeneration}
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
            message="Prompt generation will analyze your schema and documents"
            description={
              generationType === "with_deps"
                ? "With dependencies mode will auto-process missing prerequisites"
                : "Requires schema and document summaries to be available"
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
                  label: "Regular - Requires schema and summaries",
                  value: "regular",
                },
                {
                  label: "With Dependencies - Auto-handle prerequisites",
                  value: "with_deps",
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

      {/* Save Prompt Modal */}
      <Modal
        title="Save Prompt Version"
        open={saveModalVisible}
        onCancel={() => {
          setSaveModalVisible(false);
          saveForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={saveForm}
          layout="vertical"
          onFinish={handleSavePromptSubmit}
        >
          <Form.Item
            name="short_desc"
            label="Short Description"
            rules={[
              { required: true, message: "Please enter a short description" },
            ]}
          >
            <Input placeholder="Brief summary of changes" />
          </Form.Item>

          <Form.Item name="long_desc" label="Long Description">
            <TextArea
              rows={4}
              placeholder="Detailed description of what changed and why"
            />
          </Form.Item>

          <Form.Item name="base_version" label="Base Version" hidden>
            <Input type="number" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: "right" }}>
            <Space>
              <Button
                onClick={() => {
                  setSaveModalVisible(false);
                  saveForm.resetFields();
                }}
              >
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={saving}>
                Save
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Tune Prompt Modal */}
      <Modal
        title="Tune Prompt for Field"
        open={tuneModalVisible}
        onCancel={() => setTuneModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setTuneModalVisible(false)}>
            Cancel
          </Button>,
          <Button
            key="tune"
            type="primary"
            onClick={startTuning}
            disabled={!selectedConnector || !tuneFieldPath}
          >
            Start Tuning
          </Button>,
        ]}
      >
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            message="Prompt tuning will optimize the prompt for a specific field"
            description="This uses iterative refinement to improve extraction accuracy"
          />

          <div>
            <Text strong>Field Path:</Text>
            <Input
              value={tuneFieldPath}
              onChange={(e) => setTuneFieldPath(e.target.value)}
              placeholder="e.g., invoice.total_amount"
              style={{ marginTop: "8px" }}
            />
          </div>

          <div>
            <Text strong>Tuning Strategy:</Text>
            <Select
              value={tuneStrategy}
              onChange={setTuneStrategy}
              style={{ width: "100%", marginTop: "8px" }}
              options={[
                {
                  label: "Single Agent - Fast",
                  value: "single",
                },
                {
                  label: "Multi-Agent - More thorough",
                  value: "multiagent",
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

      {/* History Drawer */}
      <Drawer
        title="Prompt History"
        placement="right"
        width={500}
        open={historyVisible}
        onClose={() => setHistoryVisible(false)}
      >
        {loadingHistory ? (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <Spin size="large" />
          </div>
        ) : (
          <List
            dataSource={promptHistory}
            renderItem={(prompt) => (
              <List.Item
                key={prompt.version}
                actions={[
                  <Button
                    key="load"
                    size="small"
                    onClick={() => handleLoadVersion(prompt.version)}
                  >
                    Load
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>v{prompt.version}</Text>
                      {prompt.version === latestPrompt?.version && (
                        <Tag icon={<CheckCircleOutlined />} color="success">
                          Current
                        </Tag>
                      )}
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size="small">
                      <Text>{prompt.short_desc}</Text>
                      {prompt.accuracy !== null &&
                        prompt.accuracy !== undefined && (
                          <Badge
                            status={
                              prompt.accuracy >= 90
                                ? "success"
                                : prompt.accuracy >= 70
                                ? "warning"
                                : "error"
                            }
                            text={`Accuracy: ${Math.round(prompt.accuracy)}%`}
                          />
                        )}
                      <Text type="secondary">
                        {new Date(prompt.created_at).toLocaleString()}
                      </Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </div>
  );
}

PromptTab.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export default PromptTab;
