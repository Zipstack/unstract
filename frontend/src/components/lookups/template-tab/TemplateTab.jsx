import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import {
  Button,
  Card,
  Form,
  Input,
  Select,
  Space,
  Typography,
  Tag,
  Divider,
  Modal,
  Alert,
} from "antd";
import {
  SaveOutlined,
  PlayCircleOutlined,
  CheckOutlined,
} from "@ant-design/icons";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./TemplateTab.css";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

export function TemplateTab({ project, onUpdate }) {
  const [template, setTemplate] = useState(null);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [variables, setVariables] = useState([]);
  const [llmAdapters, setLlmAdapters] = useState([]);
  const [loadingLLMs, setLoadingLLMs] = useState(false);
  const [form] = Form.useForm();

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchLLMAdapters();
  }, [sessionDetails?.orgId]);

  useEffect(() => {
    if (project.template) {
      fetchTemplate();
    }
  }, [project.template]);

  const fetchLLMAdapters = async () => {
    if (!sessionDetails?.orgId) return;

    setLoadingLLMs(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails.orgId}/adapter/?adapter_type=LLM`
      );
      setLlmAdapters(response.data || []);
    } catch (error) {
      console.error("Failed to fetch LLM adapters:", error);
      setAlertDetails({
        type: "warning",
        content:
          "Failed to load configured LLMs. Please configure LLMs in Platform Settings.",
      });
    } finally {
      setLoadingLLMs(false);
    }
  };

  const fetchTemplate = async () => {
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-templates/${project.template.id}/`
      );
      setTemplate(response.data);
      form.setFieldsValue({
        name: response.data.name,
        template_text: response.data.template_text,
        llm_adapter_id: response.data.llm_config?.adapter_id,
      });
      extractVariables(response.data.template_text);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to fetch template",
      });
    }
  };

  const extractVariables = (text) => {
    const regex = /\{\{([^}]*)\}\}/g;
    const found = [];
    let match;
    while ((match = regex.exec(text)) !== null) {
      if (match[1] && match[1] !== "reference_data") {
        found.push(match[1]);
      }
    }
    setVariables([...new Set(found)]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        template_text: values.template_text,
        llm_config: {
          adapter_id: values.llm_adapter_id,
        },
        is_active: true,
        project: project.id,
      };

      const headers = {
        "X-CSRFToken": sessionDetails?.csrfToken,
      };

      if (template) {
        // Update existing
        await axiosPrivate.patch(
          `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-templates/${template.id}/`,
          payload,
          { headers }
        );
      } else {
        // Create new
        await axiosPrivate.post(
          `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-templates/`,
          payload,
          { headers }
        );
        // Template is automatically linked to project via the OneToOneField
      }

      setAlertDetails({
        type: "success",
        content: "Template saved successfully",
      });
      onUpdate();
      fetchTemplate();
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to save template",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    try {
      const templateText = form.getFieldValue("template_text");
      const response = await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-templates/validate/`,
        {
          template_text: templateText,
          sample_data: {},
          sample_reference: "Sample reference data",
        }
      );

      if (response.data.valid) {
        setAlertDetails({
          type: "success",
          content: "Template is valid",
        });
        setVariables(response.data.variables_found || []);
      } else {
        setAlertDetails({
          type: "error",
          content: response.data.error || "Template validation failed",
        });
      }
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to validate template",
      });
    } finally {
      setValidating(false);
    }
  };

  const handleTest = async (testData) => {
    try {
      const response = await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/execute/`,
        {
          input_data: testData,
          use_cache: false,
          timeout_seconds: 30,
        }
      );

      Modal.success({
        title: "Test Execution Successful",
        content: (
          <div>
            <Paragraph>Enrichment completed successfully!</Paragraph>
            <pre style={{ background: "#f5f5f5", padding: 8, borderRadius: 4 }}>
              {JSON.stringify(response.data.lookup_enrichment, null, 2)}
            </pre>
          </div>
        ),
        width: 600,
      });
    } catch (error) {
      Modal.error({
        title: "Test Execution Failed",
        content: error.response?.data?.error || "Failed to execute test",
      });
    }
  };

  return (
    <div className="template-tab">
      <Title level={4}>Prompt Template</Title>
      <Text type="secondary">
        Configure the prompt template for LLM enrichment
      </Text>

      <Divider />

      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="Template Name"
          rules={[{ required: true, message: "Please enter template name" }]}
        >
          <Input placeholder="e.g., Vendor Canonicalization Template" />
        </Form.Item>

        <Form.Item
          name="template_text"
          label="Template Text"
          rules={[
            { required: true, message: "Please enter template text" },
            {
              validator: (_, value) => {
                if (!value || value.includes("{{reference_data}}")) {
                  return Promise.resolve();
                }
                return Promise.reject(
                  new Error(
                    "Template must contain {{reference_data}} placeholder"
                  )
                );
              },
            },
          ]}
        >
          <TextArea
            rows={10}
            placeholder={`Extract vendor information from the input:

Vendor Name: {{vendor_name}}

Reference Data:
{{reference_data}}

Please canonicalize the vendor name and provide the following:
- Canonical vendor name
- Vendor category
- Confidence score (0-1)

Return as JSON.`}
            onChange={(e) => extractVariables(e.target.value)}
          />
        </Form.Item>

        {variables.length > 0 && (
          <Alert
            message="Detected Variables"
            description={
              <Space wrap>
                {variables.map((variable) => (
                  <Tag key={variable} color="blue">
                    {`{{${variable}}}`}
                  </Tag>
                ))}
              </Space>
            }
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Card title="LLM Configuration" size="small">
          <Form.Item
            name="llm_adapter_id"
            label="Configured LLM"
            rules={[{ required: true, message: "Please select an LLM" }]}
            extra="Select from your configured LLMs in Platform Settings"
          >
            <Select
              placeholder="Select configured LLM"
              loading={loadingLLMs}
              disabled={loadingLLMs || llmAdapters.length === 0}
              notFoundContent={
                llmAdapters.length === 0
                  ? "No LLMs configured. Please configure LLMs in Platform Settings."
                  : "Loading..."
              }
              options={llmAdapters.map((adapter) => ({
                value: adapter.id,
                label: `${adapter.adapter_name} (${adapter.adapter_type})`,
              }))}
            />
          </Form.Item>
        </Card>

        <Space style={{ marginTop: 24 }}>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={saving}
          >
            Save Template
          </Button>
          <Button
            icon={<CheckOutlined />}
            onClick={handleValidate}
            loading={validating}
          >
            Validate
          </Button>
          <Button
            icon={<PlayCircleOutlined />}
            onClick={() => setTestModalOpen(true)}
          >
            Test
          </Button>
        </Space>
      </Form>

      <Modal
        title="Test Template"
        open={testModalOpen}
        onCancel={() => setTestModalOpen(false)}
        onOk={() => {
          const testData = {};
          variables.forEach((v) => {
            const value = document.getElementById(`test-${v}`)?.value;
            if (value) testData[v] = value;
          });
          handleTest(testData);
          setTestModalOpen(false);
        }}
        width={600}
      >
        <Alert
          message="Enter test values for variables"
          description="These values will be used to test the template execution"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Space direction="vertical" style={{ width: "100%" }}>
          {variables.map((variable) => (
            <div key={variable}>
              <label>{variable}:</label>
              <Input
                id={`test-${variable}`}
                placeholder={`Enter test value for ${variable}`}
              />
            </div>
          ))}
        </Space>
      </Modal>
    </div>
  );
}

TemplateTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
    template: PropTypes.object,
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};
