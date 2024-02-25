import { InfoCircleOutlined } from "@ant-design/icons";
import {
  Checkbox,
  Form,
  Modal,
  Space,
  Switch,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";

function EvalModal({ open, setOpen, promptDetails, handleChange }) {
  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      maskClosable={false}
      footer={null}
      centered
    >
      <SpaceWrapper>
        <Typography.Text className="add-cus-tool-header">
          Evaluation Settings
        </Typography.Text>
        <Form>
          <SpaceWrapper>
            <Space>
              <Switch
                size="small"
                checked={promptDetails?.evaluate}
                onChange={(value) => {
                  handleChange(value, promptDetails?.prompt_id, "evaluate");
                }}
              />
              <Typography.Text>Enable evaluation</Typography.Text>
              <Tooltip title="Evaluate the prompt response for production readiness.">
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
            <div style={{ marginBottom: "4px" }} />
            <SpaceWrapper>
              <Typography.Text strong>Quality Metrics</Typography.Text>
              <Space>
                <Space>
                  <Checkbox
                    disabled={!promptDetails?.evaluate}
                    checked={promptDetails?.eval_quality_faithfulness}
                    onChange={(e) => {
                      handleChange(
                        e.target.checked,
                        promptDetails?.prompt_id,
                        "eval_quality_faithfulness"
                      );
                    }}
                  />
                  <Typography.Text>Faithfulness</Typography.Text>
                  <Tooltip title="Evaluate if the prompt response is relevant to the retrieved context.">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
                <Space>
                  <Checkbox
                    disabled={!promptDetails?.evaluate}
                    checked={promptDetails?.eval_quality_relevance}
                    onChange={(e) => {
                      handleChange(
                        e.target.checked,
                        promptDetails?.prompt_id,
                        "eval_quality_relevance"
                      );
                    }}
                  />
                  <Typography.Text>Relevance</Typography.Text>
                  <Tooltip title="Evaluate if the prompt is relevant to the retrieved context and generated response.">
                    <InfoCircleOutlined />
                  </Tooltip>
                </Space>
              </Space>
            </SpaceWrapper>
            <div style={{ marginBottom: "4px" }} />
            <SpaceWrapper>
              <Typography.Text strong>Security Metrics</Typography.Text>
              <Space>
                <Checkbox
                  disabled={!promptDetails?.evaluate}
                  checked={promptDetails?.eval_security_pii}
                  onChange={(e) => {
                    handleChange(
                      e.target.checked,
                      promptDetails?.prompt_id,
                      "eval_security_pii"
                    );
                  }}
                />
                <Typography.Text>PII</Typography.Text>
                <Tooltip title="Evaluate if the prompt response contains Personally Identifiable Information (PII).">
                  <InfoCircleOutlined />
                </Tooltip>
              </Space>
            </SpaceWrapper>
            <div style={{ marginBottom: "4px" }} />
            <SpaceWrapper>
              <Typography.Text strong>Guidance Metrics</Typography.Text>
              <Space>
                <Checkbox
                  disabled={!promptDetails?.evaluate}
                  checked={promptDetails?.eval_guidance_toxicity}
                  onChange={(e) => {
                    handleChange(
                      e.target.checked,
                      promptDetails?.prompt_id,
                      "eval_guidance_toxicity"
                    );
                  }}
                />
                <Typography.Text>Toxicity</Typography.Text>
                <Tooltip title="Evaluate if the prompt response contains any toxic phrases.">
                  <InfoCircleOutlined />
                </Tooltip>
              </Space>
              <Space>
                <Checkbox
                  disabled={!promptDetails?.evaluate}
                  checked={promptDetails?.eval_guidance_completeness}
                  onChange={(e) => {
                    handleChange(
                      e.target.checked,
                      promptDetails?.prompt_id,
                      "eval_guidance_completeness"
                    );
                  }}
                />
                <Typography.Text>Completeness</Typography.Text>
                <Tooltip title="Evaluate if the response is complete as per requirements in prompt.">
                  <InfoCircleOutlined />
                </Tooltip>
              </Space>
            </SpaceWrapper>
          </SpaceWrapper>
        </Form>
      </SpaceWrapper>
    </Modal>
  );
}

EvalModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  promptDetails: PropTypes.object.isRequired,
  handleChange: PropTypes.func.isRequired,
};

export { EvalModal };
