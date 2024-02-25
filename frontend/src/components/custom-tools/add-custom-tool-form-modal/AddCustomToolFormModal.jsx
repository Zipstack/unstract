import { Input, Modal, Space, Typography } from "antd";
import PropTypes from "prop-types";

import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./AddCustomToolFormModal.css";

import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";

function AddCustomToolFormModal({
  open,
  setOpen,
  editItem,
  setEditItem,
  handleAddNewTool,
}) {
  const [title, setTitle] = useState("");
  const [toolName, setToolName] = useState("");
  const [author, setAuthor] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("");
  const [isEdit, setIsEdit] = useState(false);
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    setIsEdit(editItem && Object.keys(editItem)?.length > 0);
  }, [editItem]);

  useEffect(() => {
    if (!open) {
      clearForm();
    }
  }, [open]);

  useEffect(() => {
    if (isEdit) {
      setTitle("Edit Tool Information");
      setToolName(editItem?.tool_name || "");
      setAuthor(editItem?.author || "");
      setDescription(editItem?.description || "");
      setIcon(editItem?.icon || "");
      return;
    }
    setTitle("Add Tool Information");
  }, [isEdit]);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!toolName.trim() || !author.trim() || !description.trim()) {
      setAlertDetails({
        type: "error",
        content: "Please add valid values in input fields",
      });
      return;
    }

    const body = {
      tool_name: toolName,
      author: author,
      description: description,
      icon: icon,
    };
    handleAddNewTool(body)
      .then((success) => {
        setAlertDetails({
          type: "success",
          content: `${isEdit ? "Updated" : "Added"} Successfully`,
        });
        clearForm();
      })
      .catch((err) => {
        const msg = `Failed to ${isEdit ? "update" : "add"}`;
        setAlertDetails(handleException(err, msg));
      });
  };

  const clearForm = () => {
    setToolName("");
    setAuthor("");
    setDescription("");
    setIcon("");
    setEditItem({});
    setIsEdit(false);
  };

  return (
    <Modal
      className="pre-post-amble-modal"
      width={400}
      open={open}
      onCancel={() => setOpen(false)}
      footer={null}
      centered
      maskClosable={false}
    >
      <form onSubmit={handleSubmit}>
        <div className="pre-post-amble-body">
          <div>
            <Typography.Text className="add-cus-tool-header">
              {title}
            </Typography.Text>
          </div>
          <div className="add-cus-tool-gap" />
          <SpaceWrapper>
            <Typography.Text>Tool Name</Typography.Text>
            <Input
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
              required
            />
          </SpaceWrapper>
          <div className="add-cus-tool-gap" />
          <SpaceWrapper>
            <Typography.Text>Author/Org Name</Typography.Text>
            <Input
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              required
            />
          </SpaceWrapper>
          <div className="add-cus-tool-gap" />
          <SpaceWrapper>
            <Typography.Text>Description</Typography.Text>
            <Input.TextArea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />
          </SpaceWrapper>
          <div className="add-cus-tool-gap" />
          <SpaceWrapper>
            <Typography.Text>Icon</Typography.Text>
            <Input value={icon} onChange={(e) => setIcon(e.target.value)} />
            <Typography.Text type="secondary">
              Enter the name of the icon from{" "}
              <a
                href="https://fonts.google.com/icons"
                target="_blank"
                rel="noreferrer"
              >
                Google Fonts
              </a>
            </Typography.Text>
          </SpaceWrapper>
        </div>
        <div className="pre-post-amble-footer display-flex-right">
          <Space>
            <CustomButton onClick={() => setOpen(false)}>Cancel</CustomButton>
            <CustomButton htmlType="submit" type="primary">
              Save
            </CustomButton>
          </Space>
        </div>
      </form>
    </Modal>
  );
}

AddCustomToolFormModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editItem: PropTypes.object.isRequired,
  setEditItem: PropTypes.func.isRequired,
  handleAddNewTool: PropTypes.func.isRequired,
};

export { AddCustomToolFormModal };
