import { useState } from "react";
import { Form, Input, Modal, Popover, Button } from "antd";
import PropTypes from "prop-types";
import EmojiPicker from "emoji-picker-react";

import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import "./AddCustomToolFormModal.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

import { useNavigate } from "react-router-dom";
const defaultFromDetails = {
  tool_name: "",
  author: "",
  description: "",
  icon: "",
};

function AddCustomToolFormModal({
  open,
  setOpen,
  editItem,
  isEdit,
  handleAddNewTool,
}) {
  const [form] = Form.useForm();
  const [isLoading, setIsLoading] = useState(false);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [formDetails, setFormDetails] = useState(
    isEdit ? { ...editItem } : { ...defaultFromDetails }
  );
  const [icon, setIcon] = useState(isEdit ? formDetails.icon : "");
  const [backendErrors, setBackendErrors] = useState(null);
  const navigate = useNavigate();

  const updateIcon = (emoji) => {
    setIcon(emoji);
    setFormDetails((prevState) => ({
      ...prevState,
      icon: emoji,
    }));
  };

  const handleInputChange = (changedValues, allValues) => {
    setFormDetails({ ...formDetails, ...allValues });
    const changedFieldName = Object.keys(changedValues)[0];
    form.setFields([
      {
        name: changedFieldName,
        errors: [],
      },
    ]);
    setBackendErrors((prevErrors) => {
      if (prevErrors) {
        const updatedErrors = prevErrors.errors.filter(
          (error) => error.attr !== changedFieldName
        );
        return { ...prevErrors, errors: updatedErrors };
      }
      return null;
    });
  };

  const handleSubmit = (event) => {
    const body = formDetails;
    setIsLoading(true);
    handleAddNewTool(body)
      .then((success) => {
        setAlertDetails({
          type: "success",
          content: `${isEdit ? "Updated" : "Added"} Successfully`,
        });
        setOpen(false);
        clearFormDetails();
        navigate(success?.tool_id);
      })
      .catch((err) => {
        handleException(err, "", setBackendErrors);
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const clearFormDetails = () => {
    setFormDetails({ ...defaultFromDetails });
  };

  return (
    <Modal
      title={
        isEdit
          ? "Edit Prompt Studio project"
          : "Create new Prompt Studio project"
      }
      width={450}
      open={open}
      onCancel={() => {
        setOpen(false);
        setShowEmojiPicker(false);
      }}
      centered
      maskClosable={false}
      onOk={handleSubmit}
      okText={isEdit ? "Update" : "Save"}
      okButtonProps={{
        loading: isLoading,
      }}
      destroyOnClose
    >
      <Form
        form={form}
        name="myForm"
        layout="vertical"
        initialValues={formDetails}
        onValuesChange={handleInputChange}
      >
        <Form.Item
          label="Prompt Studio project name"
          name="tool_name"
          rules={[{ required: true, message: "Please enter project name" }]}
          validateStatus={
            getBackendErrorDetail("tool_name", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("tool_name", backendErrors)}
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="Author/Org Name"
          name="author"
          rules={[{ required: true, message: "Please enter Author/Org name" }]}
          validateStatus={
            getBackendErrorDetail("author", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("author", backendErrors)}
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="Description"
          name="description"
          rules={[{ required: true, message: "Please enter description" }]}
          validateStatus={
            getBackendErrorDetail("description", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("description", backendErrors)}
        >
          <Input.TextArea
            rows={4}
            showCount={true}
            maxLength={200}
            style={{ height: 100, resize: "none" }}
          />
        </Form.Item>

        <Form.Item label="Icon" name="icon">
          <Popover
            open={showEmojiPicker}
            placement="rightTop"
            arrow={false}
            trigger={"click"}
            className="emoji-modal"
            title={
              <EmojiPicker
                previewConfig={{ showPreview: false }}
                lazyLoadEmojis
                onEmojiClick={(emoji) => {
                  updateIcon(emoji.emoji);
                  setShowEmojiPicker(false);
                }}
              />
            }
          >
            <Button onClick={() => setShowEmojiPicker((prev) => !prev)}>
              {icon} {icon ? "Change" : "Choose"} Icon
            </Button>
          </Popover>
        </Form.Item>
      </Form>
    </Modal>
  );
}

AddCustomToolFormModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editItem: PropTypes.object.isRequired,
  isEdit: PropTypes.bool.isRequired,
  handleAddNewTool: PropTypes.func.isRequired,
};

export { AddCustomToolFormModal };
