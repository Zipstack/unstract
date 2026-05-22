import { Form, Input, Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useExceptionHandler } from "../../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../../store/alert-store";

import { groupsService } from "./groups-service.js";

function GroupCreateEditModal({ open, mode, group, onClose, onSaved }) {
  const service = groupsService();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        name: mode === "edit" ? group?.name : "",
        description: mode === "edit" ? group?.description : "",
      });
    }
  }, [open, mode, group, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const call =
        mode === "edit"
          ? service.updateGroup(group.id, values)
          : service.createGroup(values);
      call
        .then(() => {
          setAlertDetails({
            type: "success",
            content: mode === "edit" ? "Group updated" : "Group created",
          });
          form.resetFields();
          onSaved?.();
        })
        .catch((err) =>
          setAlertDetails(handleException(err, "Failed to save group")),
        )
        .finally(() => setSubmitting(false));
    } catch (_validationError) {
      // form validation error — Ant Design surfaces it inline
    }
  };

  return (
    <Modal
      title={mode === "edit" ? "Edit group" : "New group"}
      open={open}
      onOk={handleOk}
      confirmLoading={submitting}
      onCancel={() => {
        form.resetFields();
        onClose?.();
      }}
      centered
      okText={mode === "edit" ? "Save" : "Create"}
      maskClosable={false}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label="Name"
          name="name"
          rules={[{ required: true, message: "Group name is required" }]}
        >
          <Input maxLength={255} />
        </Form.Item>
        <Form.Item label="Description" name="description">
          <Input.TextArea rows={3} maxLength={1000} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

GroupCreateEditModal.propTypes = {
  open: PropTypes.bool.isRequired,
  mode: PropTypes.oneOf(["create", "edit"]).isRequired,
  group: PropTypes.object,
  onClose: PropTypes.func,
  onSaved: PropTypes.func,
};

export { GroupCreateEditModal };
