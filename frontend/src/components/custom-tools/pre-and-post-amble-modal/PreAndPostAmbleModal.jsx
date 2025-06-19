import { Button, Input, Space, Typography, Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState, useRef } from "react";
import { ExpandOutlined } from "@ant-design/icons";
import "./PreAndPostAmbleModal.css";

import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";

import DefaultPrompts from "./DefaultPrompts.json";

const fieldNames = {
  preamble: "PREAMBLE",
  postamble: "POSTAMBLE",
};

function PreAndPostAmbleModal({ type, handleUpdateTool }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [expandModalVisible, setExpandModalVisible] = useState(false);
  const textAreaRef = useRef(null);
  const { details, updateCustomTool, isPublicSource } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (type === fieldNames.preamble) {
      setTitle("Preamble Settings");
      setText(details?.preamble || "");
    } else if (type === fieldNames.postamble) {
      setTitle("Postamble Settings");
      setText(details?.postamble || "");
    }

    // Adjust text area height after content is set
    setTimeout(() => {
      adjustTextAreaHeight();
    }, 0);
  }, [type, details]);

  const setDefaultPrompt = () => {
    if (type === fieldNames.preamble) {
      setText(DefaultPrompts.preamble);
    } else if (type === fieldNames.postamble) {
      setText(DefaultPrompts.postamble);
    }

    // Adjust height after setting default text
    setTimeout(() => {
      adjustTextAreaHeight();
    }, 0);
  };

  const adjustTextAreaHeight = () => {
    if (textAreaRef.current) {
      const textArea = textAreaRef.current.resizableTextArea.textArea;
      // Reset height to calculate scroll height properly
      textArea.style.height = "auto";
      // Set new height based on scroll height (with min/max constraints)
      const minHeight = 80; // 80px is approx 4 rows
      const maxHeight = 300; // Max height before scrolling
      const newHeight = Math.min(
        Math.max(textArea.scrollHeight, minHeight),
        maxHeight
      );
      textArea.style.height = `${newHeight}px`;
    }
  };

  const handleTextChange = (e) => {
    setText(e.target.value);
    adjustTextAreaHeight();
  };

  const toggleExpandModal = () => {
    setExpandModalVisible(!expandModalVisible);
  };

  const handleSave = () => {
    const body = {};
    if (type === fieldNames.preamble) {
      body["preamble"] = text;
    }

    if (type === fieldNames.postamble) {
      body["postamble"] = text;
    }
    handleUpdateTool(body)
      .then((res) => {
        const data = res?.data;
        const updatedData = {
          preamble: data?.preamble || "",
          postamble: data?.postamble || "",
        };
        const updatedDetails = { ...details, ...updatedData };
        updateCustomTool({ details: updatedDetails });
        setAlertDetails({
          type: "success",
          content: "Saved successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update."));
      });
  };

  return (
    <div className="settings-body-pad-top">
      <SpaceWrapper>
        <div>
          <Typography.Text strong className="pre-post-amble-title">
            {title}
          </Typography.Text>
        </div>
        <div>
          <div className="text-area-header">
            <Typography.Text>Add {title}</Typography.Text>
          </div>
        </div>
        <div className="text-area-container">
          <div className="text-area-wrapper">
            <Input.TextArea
              ref={textAreaRef}
              rows={4}
              value={text}
              onChange={handleTextChange}
              disabled={isPublicSource}
              autoSize={{ minRows: 4 }}
            />
            <Button
              icon={<ExpandOutlined />}
              className="expand-button"
              onClick={toggleExpandModal}
              type="text"
              disabled={isPublicSource}
              title="Expand view"
            />
          </div>
          <Button
            size="small"
            type="link"
            onClick={setDefaultPrompt}
            disabled={isPublicSource}
          >
            Reset with default prompt
          </Button>

          <Modal
            title={title}
            open={expandModalVisible}
            onCancel={toggleExpandModal}
            footer={null}
            width="60%"
            className="expanded-modal-body"
            centered={true}
          >
            <Input.TextArea
              value={text}
              onChange={handleTextChange}
              disabled={isPublicSource}
              autoSize={{ minRows: 15 }}
              className="expanded-textarea"
            />
            <div className="modal-footer">
              <Button type="primary" onClick={toggleExpandModal}>
                Close
              </Button>
            </div>
          </Modal>
        </div>
        <div className="display-flex-right">
          <Space>
            <CustomButton
              type="primary"
              onClick={handleSave}
              disabled={isPublicSource}
            >
              Save
            </CustomButton>
          </Space>
        </div>
      </SpaceWrapper>
    </div>
  );
}

PreAndPostAmbleModal.propTypes = {
  type: PropTypes.string.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { PreAndPostAmbleModal };
