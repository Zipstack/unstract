import { Button, Input, Modal, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import "./PreAndPostAmbleModal.css";

import { handleException } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";

const fieldNames = {
  preamble: "PREAMBLE",
  postamble: "POSTAMBLE",
};

function PreAndPostAmbleModal({ isOpen, closeModal, type, handleUpdateTool }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const { details, updateCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    if (!isOpen) {
      setText("");
      setTitle("");
      return;
    }

    if (type === fieldNames.preamble) {
      setTitle("Preamble");
      setText(details?.preamble || "");
      return;
    }

    if (type === fieldNames.postamble) {
      setTitle("Postamble");
      setText(details?.postamble || "");
    }
  }, [isOpen]);

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
        closeModal();
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
    <Modal
      className="pre-post-amble-modal"
      open={isOpen}
      onCancel={closeModal}
      footer={null}
      centered
      maskClosable={false}
    >
      <div className="pre-post-amble-body">
        <Space direction="vertical" className="pre-post-amble-body-space">
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
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        </Space>
      </div>
      <div className="pre-post-amble-footer display-flex-right">
        <Space>
          <Button onClick={closeModal}>Cancel</Button>
          <CustomButton type="primary" onClick={handleSave}>
            Save
          </CustomButton>
        </Space>
      </div>
    </Modal>
  );
}

PreAndPostAmbleModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  closeModal: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { PreAndPostAmbleModal };
