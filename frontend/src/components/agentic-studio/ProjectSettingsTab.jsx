import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import {
  Card,
  Form,
  Input,
  Button,
  Space,
  Typography,
  Select,
  Divider,
  Alert,
} from "antd";
import { SaveOutlined } from "@ant-design/icons";

import {
  projectsApi,
  connectorsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";
import { useSessionStore } from "../../store/session-store";

const { Title, Text } = Typography;
const { TextArea } = Input;

function ProjectSettingsTab({ project, onUpdate }) {
  const { sessionDetails } = useSessionStore();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [connectors, setConnectors] = useState([]);
  const [loadingConnectors, setLoadingConnectors] = useState(false);

  useEffect(() => {
    if (project) {
      form.setFieldsValue({
        name: project.name,
        description: project.description,
        llm_connector_id: project.llm_connector_id,
        agent_llm_connector_id: project.agent_llm_connector_id,
        lightweight_llm_connector_id: project.lightweight_llm_connector_id,
        llmwhisperer_connector_id: project.llmwhisperer_connector_id,
      });
    }
    loadConnectors();
  }, [project, form]);

  const loadConnectors = async () => {
    try {
      setLoadingConnectors(true);
      const data = await connectorsApi.list(sessionDetails?.orgId);
      setConnectors(data);
    } catch (error) {
      showApiError(error, "Failed to load connectors");
    } finally {
      setLoadingConnectors(false);
    }
  };

  const handleSave = async (values) => {
    try {
      setSaving(true);
      await projectsApi.updateSettings(project.id, values);
      showApiSuccess("Project settings saved successfully");
      if (onUpdate) {
        onUpdate();
      }
    } catch (error) {
      showApiError(error, "Failed to save project settings");
    } finally {
      setSaving(false);
    }
  };

  // Filter adapters by type
  const llmConnectors = connectors.filter((c) => c.adapter_type === "LLM");
  const llmWhispererConnectors = connectors.filter(
    (c) => c.adapter_type === "X2TEXT"
  );

  return (
    <div style={{ height: "calc(100vh - 200px)", overflow: "auto" }}>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {/* Header */}
        <Card>
          <Title level={4} style={{ margin: 0, marginBottom: "8px" }}>
            Project Settings
          </Title>
          <Text type="secondary">
            Configure project details and LLM connectors
          </Text>
        </Card>

        {/* Project Details */}
        <Card title="Project Details">
          <Form form={form} layout="vertical" onFinish={handleSave}>
            <Form.Item
              label="Project Name"
              name="name"
              rules={[{ required: true, message: "Please enter project name" }]}
            >
              <Input placeholder="e.g., Invoice Processing" />
            </Form.Item>

            <Form.Item label="Description" name="description">
              <TextArea
                rows={3}
                placeholder="Describe the purpose of this project"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={saving}
              >
                Save Changes
              </Button>
            </Form.Item>
          </Form>
        </Card>

        {/* LLM Connector Configuration */}
        <Card title="LLM Connector Configuration">
          <Alert
            type="info"
            showIcon
            message="Configure LLM connectors for different purposes"
            description="Extractor is used for data extraction, Agent for complex reasoning, and Lightweight for simple tasks."
            style={{ marginBottom: "24px" }}
          />

          <Form form={form} layout="vertical" onFinish={handleSave}>
            <Form.Item
              label="Extractor LLM"
              name="llm_connector_id"
              tooltip="Primary LLM used for data extraction"
            >
              <Select
                placeholder="Select extractor LLM connector"
                loading={loadingConnectors}
                allowClear
                options={llmConnectors.map((c) => ({
                  label: c.adapter_name,
                  value: c.id,
                }))}
              />
            </Form.Item>

            <Form.Item
              label="Agent LLM"
              name="agent_llm_connector_id"
              tooltip="LLM used for agent-based tasks and reasoning"
            >
              <Select
                placeholder="Select agent LLM connector"
                loading={loadingConnectors}
                allowClear
                options={llmConnectors.map((c) => ({
                  label: c.adapter_name,
                  value: c.id,
                }))}
              />
            </Form.Item>

            <Form.Item
              label="Lightweight LLM"
              name="lightweight_llm_connector_id"
              tooltip="LLM used for lightweight tasks like metadata generation"
            >
              <Select
                placeholder="Select lightweight LLM connector"
                loading={loadingConnectors}
                allowClear
                options={llmConnectors.map((c) => ({
                  label: c.adapter_name,
                  value: c.id,
                }))}
              />
            </Form.Item>

            <Divider />

            <Form.Item
              label="LLMWhisperer Connector"
              name="llmwhisperer_connector_id"
              tooltip="Connector for document text extraction (OCR)"
            >
              <Select
                placeholder="Select LLMWhisperer connector"
                loading={loadingConnectors}
                allowClear
                options={llmWhispererConnectors.map((c) => ({
                  label: c.adapter_name,
                  value: c.id,
                }))}
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={saving}
              >
                Save Connector Settings
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Space>
    </div>
  );
}

ProjectSettingsTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
    name: PropTypes.string,
    description: PropTypes.string,
    llm_connector_id: PropTypes.string,
    agent_llm_connector_id: PropTypes.string,
    lightweight_llm_connector_id: PropTypes.string,
    llmwhisperer_connector_id: PropTypes.string,
  }).isRequired,
  onUpdate: PropTypes.func,
};

export default ProjectSettingsTab;
