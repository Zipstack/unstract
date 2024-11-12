import { Button, Input, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
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
  const { details, updateCustomTool, isPublicSource } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (type === fieldNames.preamble) {
      setTitle("Preamble Settings");
      setText(details?.preamble || "");
      return;
    }

    if (type === fieldNames.postamble) {
      setTitle("Postamble Settings");
      setText(details?.postamble || "");
    }
  }, [type]);

  const setDefaultPrompt = () => {
    if (type === fieldNames.preamble) {
      setText(DefaultPrompts.preamble);
      return;
    }

    if (type === fieldNames.postamble) {
      setText(DefaultPrompts.postamble);
    }
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
          <div>
            <Typography.Text>Add {title}</Typography.Text>
          </div>
        </div>
        <div>
          <Input.TextArea
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={isPublicSource}
          />
          <Button
            size="small"
            type="link"
            onClick={setDefaultPrompt}
            disabled={isPublicSource}
          >
            Reset with default prompt
          </Button>
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
