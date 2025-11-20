import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Modal, Form, Input, Button, message } from "antd";
import { ThunderboltOutlined, LoadingOutlined } from "@ant-design/icons";

import { useMockApi } from "../hooks/useMockApi";

const { TextArea } = Input;

const SavePromptModal = ({
  visible,
  onClose,
  projectId,
  promptText,
  baseVersion,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { generateMetadata, createPrompt } = useMockApi();

  // Reset form when modal closes
  useEffect(() => {
    if (!visible) {
      form.resetFields();
    }
  }, [visible, form]);

  // Handle AI metadata generation
  const handleGenerateMetadata = async () => {
    setIsGenerating(true);
    try {
      // TODO: Replace with actual API call
      const metadata = await generateMetadata(promptText);

      if (metadata.generated) {
        form.setFieldsValue({
          short_desc: metadata.short_desc,
          long_desc: metadata.long_desc,
        });
        message.success("Metadata generated successfully");
      } else {
        message.warning("Using fallback metadata");
      }
    } catch (error) {
      message.error("Failed to generate metadata");
      console.error("Generate metadata error:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  // Handle form submission
  const handleSave = async (values) => {
    setIsSaving(true);
    try {
      // TODO: Replace with actual API call
      await createPrompt(projectId, {
        prompt_text: promptText,
        short_desc: values.short_desc,
        long_desc: values.long_desc,
        base_version: baseVersion,
      });

      message.success("Prompt version saved successfully");
      form.resetFields();
      onSuccess();
      onClose();
    } catch (error) {
      message.error("Failed to save prompt");
      console.error("Save prompt error:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title="Save Prompt Version"
      open={visible}
      onCancel={handleCancel}
      footer={null}
      width={700}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSave}
        autoComplete="off"
      >
        <Form.Item label="Base Version">
          <Input value={`v${baseVersion}`} disabled />
        </Form.Item>

        <Form.Item
          label={
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                width: "100%",
              }}
            >
              <span>Short Description (max 50 chars)</span>
              <Button
                type="primary"
                size="small"
                icon={
                  isGenerating ? <LoadingOutlined /> : <ThunderboltOutlined />
                }
                onClick={handleGenerateMetadata}
                loading={isGenerating}
                disabled={isGenerating}
                style={{
                  marginLeft: "auto",
                  backgroundColor: "#722ed1",
                  borderColor: "#722ed1",
                }}
              >
                Generate with AI
              </Button>
            </div>
          }
          name="short_desc"
          rules={[
            { required: true, message: "Please enter a short description" },
            { max: 50, message: "Maximum 50 characters allowed" },
          ]}
        >
          <Input
            placeholder="Brief description of changes"
            maxLength={50}
            showCount
          />
        </Form.Item>

        <Form.Item
          label="Long Description (max 255 chars)"
          name="long_desc"
          rules={[
            { required: true, message: "Please enter a long description" },
            { max: 255, message: "Maximum 255 characters allowed" },
          ]}
        >
          <TextArea
            placeholder="Detailed explanation of changes and improvements"
            rows={4}
            maxLength={255}
            showCount
          />
        </Form.Item>

        <Form.Item style={{ marginBottom: 0 }}>
          <div
            style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}
          >
            <Button onClick={handleCancel} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="primary" htmlType="submit" loading={isSaving}>
              Save Version
            </Button>
          </div>
        </Form.Item>
      </Form>
    </Modal>
  );
};

SavePromptModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  projectId: PropTypes.string.isRequired,
  promptText: PropTypes.string.isRequired,
  baseVersion: PropTypes.number.isRequired,
  onSuccess: PropTypes.func.isRequired,
};

export default SavePromptModal;
