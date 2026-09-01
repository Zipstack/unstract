import EmojiPicker from "emoji-picker-react";
import PropTypes from "prop-types";
import { useState } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Form } from "@/components/ui/shims/antd-form";
import { Input } from "@/components/ui/shims/antd-inputs";
import { Modal, Popover } from "@/components/ui/shims/antd-overlays";

import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import "./AddCustomToolFormModal.css";

import { useNavigate } from "react-router-dom";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

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
    isEdit ? { ...editItem } : { ...defaultFromDetails },
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
          (error) => error.attr !== changedFieldName,
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
      data-testid="add-prompt-project-modal"
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
            // Without this the picker is a controlled popover with no way to
            // report a close, so Esc and clicking outside did nothing.
            onOpenChange={setShowEmojiPicker}
            /*
             * `rightTop` threw the picker out past the modal's right edge,
             * where it was sliced off mid-column. Opening downward from the
             * trigger keeps its full width on screen; Radix still flips it
             * upward automatically when there is no room below.
             */
            placement="bottomLeft"
            arrow={false}
            trigger={"click"}
            data-testid="add-prompt-project-icon-popover"
            className="emoji-modal"
            title={
              <EmojiPicker
                previewConfig={{ showPreview: false }}
                lazyLoadEmojis
                /*
                 * `height` is the picker's TOTAL height, and its search box,
                 * category bar and padding take ~132px of it — so at 320 the
                 * scrollable emoji grid was only 188px inside a 326px panel.
                 * The wheel then appeared dead: it works only while the
                 * pointer is inside that short strip, and most of the visible
                 * panel is not it.
                 *
                 * 450 gives the grid ~318px, filling the panel. The popover
                 * caps itself at `--radix-popover-content-available-height`
                 * and the picker scrolls internally, so a short viewport
                 * shrinks the panel rather than clipping the picker.
                 */
                height={450}
                onEmojiClick={(emoji) => {
                  updateIcon(emoji.emoji);
                  setShowEmojiPicker(false);
                }}
              />
            }
          >
            {/*
             * No onClick here: the Popover trigger already toggles `open` and
             * reports it through onOpenChange. Doing both meant two state
             * updates per click — Radix's (open -> false) and this one
             * (!prev), which race and can leave the picker unable to reopen.
             */}
            <Button data-testid="add-prompt-project-icon-btn">
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
