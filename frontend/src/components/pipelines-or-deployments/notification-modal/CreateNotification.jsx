import { Button, Form, Input, Select, Space } from "antd";
import PropTypes from "prop-types";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { useEffect, useState } from "react";

const DEFAULT_FORM_DETAILS = {
  name: "",
  authorization_type: "BEARER",
  notification_type: "WEBHOOK",
  platform: "SLACK",
  authorization_header: "",
  authorization_key: "",
  is_active: false,
  max_retries: 0,
  pipeline: "",
  api: "",
  url: "",
};

const NOTIFICATION_TYPE_ITEMS = [
  {
    value: "WEBHOOK",
    label: "WEBHOOK",
  },
];

const PLATFORM_TYPES = [
  {
    value: "SLACK",
    label: "SLACK",
  },
  {
    value: "API",
    label: "API",
  },
];

const AUTHORIZATION_TYPES = [
  {
    value: "BEARER",
    label: "BEARER",
  },
  {
    value: "API_KEY",
    label: "API_KEY",
  },
  {
    value: "CUSTOM_HEADER",
    label: "CUSTOM_HEADER",
  },
  {
    value: "NONE",
    label: "NONE",
  },
];

function CreateNotification({
  setIsForm,
  type,
  id,
  isLoading,
  handleSubmit,
  handleUpdate,
  editDetails,
}) {
  const [form] = Form.useForm();
  const [formDetails, setFormDetails] = useState(DEFAULT_FORM_DETAILS);
  const [backendErrors, setBackendErrors] = useState(null);

  useEffect(() => {
    if (editDetails) {
      setFormDetails(editDetails);
    }
  }, [editDetails]);

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

  const triggerSubmit = () => {
    const body = { ...formDetails };
    body[type] = id;

    if (editDetails) {
      handleUpdate(body, editDetails?.id);
    } else {
      handleSubmit(body);
    }
  };

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={formDetails}
      onValuesChange={handleInputChange}
      onFinish={triggerSubmit}
    >
      <Form.Item
        label="Name"
        name="name"
        rules={[{ required: true, message: "Please enter name" }]}
        validateStatus={
          getBackendErrorDetail("name", backendErrors) ? "error" : ""
        }
        help={getBackendErrorDetail("name", backendErrors)}
      >
        <Input />
      </Form.Item>
      <Form.Item
        label="Url"
        name="url"
        rules={[{ required: true, message: "Please enter URL" }]}
        validateStatus={
          getBackendErrorDetail("url", backendErrors) ? "error" : ""
        }
        help={getBackendErrorDetail("url", backendErrors)}
      >
        <Input />
      </Form.Item>
      <Form.Item
        label="Notification Type"
        name="notification_type"
        validateStatus={
          getBackendErrorDetail("notification_type", backendErrors)
            ? "error"
            : ""
        }
        help={getBackendErrorDetail("notification_type", backendErrors)}
      >
        <Select options={NOTIFICATION_TYPE_ITEMS} />
      </Form.Item>
      <Form.Item
        label="Platform"
        name="platform"
        validateStatus={
          getBackendErrorDetail("platform", backendErrors) ? "error" : ""
        }
        help={getBackendErrorDetail("platform", backendErrors)}
      >
        <Select options={PLATFORM_TYPES} />
      </Form.Item>
      <Form.Item
        label="Authorization Type"
        name="authorization_type"
        validateStatus={
          getBackendErrorDetail("authorization_type", backendErrors)
            ? "error"
            : ""
        }
        help={getBackendErrorDetail("authorization_type", backendErrors)}
      >
        <Select options={AUTHORIZATION_TYPES} />
      </Form.Item>
      <Form.Item
        label="Authorization Header"
        name="authorization_header"
        validateStatus={
          getBackendErrorDetail("authorization_header", backendErrors)
            ? "error"
            : ""
        }
        help={getBackendErrorDetail("authorization_header", backendErrors)}
      >
        <Input />
      </Form.Item>
      <Form.Item
        label="Authorization Key"
        name="authorization_key"
        validateStatus={
          getBackendErrorDetail("authorization_key", backendErrors)
            ? "error"
            : ""
        }
        help={getBackendErrorDetail("authorization_key", backendErrors)}
      >
        <Input />
      </Form.Item>
      <Form.Item
        label="Max Retires"
        name="max_retries"
        validateStatus={
          getBackendErrorDetail("max_retries", backendErrors) ? "error" : ""
        }
        help={getBackendErrorDetail("max_retries", backendErrors)}
      >
        <Input type="number" />
      </Form.Item>
      <Form.Item className="display-flex-right">
        <Space>
          <Button onClick={() => setIsForm(false)}>Cancel</Button>
          <Button type="primary" htmlType="submit" loading={isLoading}>
            {editDetails ? "Update" : "Create"} Notification
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
}

CreateNotification.propTypes = {
  setIsForm: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  id: PropTypes.string.isRequired,
  isLoading: PropTypes.bool.isRequired,
  handleSubmit: PropTypes.func.isRequired,
  handleUpdate: PropTypes.func.isRequired,
  editDetails: PropTypes.object,
};

export { CreateNotification };
