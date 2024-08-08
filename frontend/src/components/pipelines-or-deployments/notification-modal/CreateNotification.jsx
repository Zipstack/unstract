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
  const [resetForm, setResetForm] = useState(false);

  useEffect(() => {
    if (editDetails) {
      setFormDetails(editDetails);
      setResetForm(true);
    }
  }, [editDetails]);

  useEffect(() => {
    if (resetForm) {
      form.resetFields();
      setResetForm(false);
    }
  }, [formDetails]);

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

  const formItems = [
    {
      label: "Name",
      name: "name",
      rules: [{ required: true, message: "Please enter name" }],
      component: <Input />,
    },
    {
      label: "Url",
      name: "url",
      rules: [{ required: true, message: "Please enter URL" }],
      component: <Input />,
    },
    {
      label: "Notification Type",
      name: "notification_type",
      component: <Select options={NOTIFICATION_TYPE_ITEMS} />,
    },
    {
      label: "Platform",
      name: "platform",
      component: <Select options={PLATFORM_TYPES} />,
    },
    {
      label: "Authorization Type",
      name: "authorization_type",
      component: <Select options={AUTHORIZATION_TYPES} />,
    },
    {
      label: "Authorization Header",
      name: "authorization_header",
      component: <Input />,
    },
    {
      label: "Authorization Key",
      name: "authorization_key",
      component: <Input />,
    },
    {
      label: "Max Retries",
      name: "max_retries",
      component: <Input type="number" />,
    },
  ];

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={formDetails}
      onValuesChange={handleInputChange}
      onFinish={triggerSubmit}
    >
      {formItems.map(({ label, name, rules, component }) => (
        <Form.Item
          key={name}
          label={label}
          name={name}
          rules={rules}
          validateStatus={
            getBackendErrorDetail(name, backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail(name, backendErrors)}
        >
          {component}
        </Form.Item>
      ))}
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
