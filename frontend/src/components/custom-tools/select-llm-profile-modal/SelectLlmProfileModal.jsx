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

function SelectLlmProfileModal({
  open,
  setOpen,
  llmItems,
  setBtnText,
  handleUpdateTool,
}) {
  const [selectedLlm, setSelectedLlm] = useState("");
  const [isContext, setIsContext] = useState(false);
  const { details } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    setIsContext(details?.summarize_context);
  }, []);

  useEffect(() => {
    if (!selectedLlm) {
      setBtnText("");
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

  const handleLlmProfileChange = (fieldName, value) => {
    const body = {
      [fieldName]: value,
    };
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
      })
      .finally(() => {
        if (fieldName === "summarize_context") {
          setIsContext(value);
        }
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
          <Form.Item label="Select LLM Profile" name="summarize_llm_profile">
            <Select
              placeholder="Select Eval LLM"
              defaultValue={selectedLlm}
              options={llmItems}
              onChange={(value) =>
                handleLlmProfileChange("summarize_llm_profile", value)
              }
            />
          </Form.Item>
          <Form.Item label="Prompt">
            <Input.TextArea
              rows={3}
              placeholder="Enter Prompt"
              name="summarize_prompt"
              defaultValue={details?.summarize_prompt}
              onChange={onSearchDebounce}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Switch
                defaultValue={details?.summarize_context}
                size="small"
                onChange={(value) =>
                  handleLlmProfileChange("summarize_context", value)
                }
              />
              <Typography.Text>Summarize Context</Typography.Text>
            </Space>
          </Form.Item>
          <div style={{ margin: "10px 0px" }} />
          <Form.Item name="summarize_as_source">
            <Space>
              <Checkbox
                defaultChecked={details?.summarize_as_source}
                disabled={!isContext}
                size="small"
                onChange={(e) =>
                  handleLlmProfileChange(
                    "summarize_as_source",
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
