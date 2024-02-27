import {
  Checkbox,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useCallback, useEffect, useState } from "react";
import debounce from "lodash/debounce";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { handleException } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";

const fieldNames = {
  SUMMARIZE_LLM_PROFILE: "summarize_llm_profile",
  SUMMARIZE_PROMPT: "summarize_prompt",
  SUMMARIZE_CONTEXT: "summarize_context",
  SUMMARIZE_AS_SOURCE: "summarize_as_source",
};
function SelectLlmProfileModal({
  open,
  setOpen,
  llmItems,
  setBtnText,
  handleUpdateTool,
}) {
  const [selectedLlm, setSelectedLlm] = useState("");
  const [prompt, setPrompt] = useState("");
  const [isContext, setIsContext] = useState(false);
  const [isSource, setIsSource] = useState(false);
  const { details } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    setIsContext(details?.summarize_context);
    setIsSource(details?.summarize_as_source);
  }, []);

  useEffect(() => {
    if (!selectedLlm) {
      setBtnText("");

      // If the LLM is not selected, the context needs to be set to false and disabled in the UI
      if (isContext) {
        handleLlmProfileChange(fieldNames.SUMMARIZE_CONTEXT, false);
      }
      return;
    }

    const llmItem = [...llmItems].find((item) => item?.value === selectedLlm);
    setBtnText(llmItem?.label || "");
  }, [selectedLlm]);

  useEffect(() => {
    if (llmItems?.length) {
      setSelectedLlm(details?.summarize_llm_profile);
    }
  }, [llmItems]);

  const handleStateUpdate = (fieldName, value) => {
    if (fieldName === fieldNames.SUMMARIZE_LLM_PROFILE) {
      setSelectedLlm(value);
    }

    if (fieldName === fieldNames.SUMMARIZE_PROMPT) {
      setPrompt(value);
    }

    if (fieldName === fieldNames.SUMMARIZE_CONTEXT) {
      setIsContext(value);
    }

    if (fieldName === fieldNames.SUMMARIZE_AS_SOURCE) {
      setIsSource(value);
    }
  };

  const handleLlmProfileChange = (fieldName, value) => {
    handleStateUpdate(fieldName, value);
    const body = {
      [fieldName]: value,
    };

    if (fieldName === fieldNames.SUMMARIZE_CONTEXT && !value) {
      body[fieldNames.SUMMARIZE_AS_SOURCE] = false;
      handleStateUpdate(fieldNames.SUMMARIZE_AS_SOURCE, false);
    }

    handleUpdateTool(body)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Successfully updated the LLM profile",
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to update the LLM profile")
        );
      });
  };

  const onSearchDebounce = useCallback(
    debounce((event) => {
      handleLlmProfileChange(event.target.name, event.target.value);
    }, 1000),
    []
  );

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(null)}
      maskClosable={false}
      centered
      footer={null}
    >
      <div className="pre-post-amble-body">
        <div>
          <Typography.Text strong className="pre-post-amble-title">
            Summarize Manager
          </Typography.Text>
        </div>
        <Form layout="vertical" size="small">
          <Form.Item label="Select LLM Profile">
            <Select
              placeholder="Select Eval LLM"
              defaultValue={selectedLlm}
              options={llmItems}
              onChange={(value) =>
                handleLlmProfileChange(fieldNames.SUMMARIZE_LLM_PROFILE, value)
              }
            />
          </Form.Item>
          <Form.Item label="Prompt">
            <Input.TextArea
              rows={3}
              placeholder="Enter Prompt"
              name={fieldNames.SUMMARIZE_PROMPT}
              defaultValue={prompt}
              onChange={onSearchDebounce}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Switch
                defaultValue={isContext}
                disabled={!selectedLlm}
                size="small"
                onChange={(value) =>
                  handleLlmProfileChange(fieldNames.SUMMARIZE_CONTEXT, value)
                }
              />
              <Typography.Text>Summarize Context</Typography.Text>
            </Space>
          </Form.Item>
          <div style={{ margin: "10px 0px" }} />
          <Form.Item>
            <Space>
              <Checkbox
                checked={isSource}
                disabled={!isContext || !selectedLlm}
                size="small"
                onChange={(e) =>
                  handleLlmProfileChange(
                    fieldNames.SUMMARIZE_AS_SOURCE,
                    e.target.checked
                  )
                }
              />
              <Typography.Text>Use summarize context as source</Typography.Text>
            </Space>
          </Form.Item>
        </Form>
      </div>
    </Modal>
  );
}

SelectLlmProfileModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  llmItems: PropTypes.array.isRequired,
  setBtnText: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { SelectLlmProfileModal };
