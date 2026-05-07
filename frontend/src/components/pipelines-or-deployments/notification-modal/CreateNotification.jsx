import { Button, Checkbox, Form, Input, Select, Space } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";

// Used only when the org's batch interval can't be fetched (network or auth
// failure). Backend's env-derived default is also 30 min, so this matches.
const FALLBACK_BATCH_INTERVAL_MINUTES = 30;

const DEFAULT_FORM_DETAILS = {
  name: "",
  authorization_type: "BEARER",
  notification_type: "WEBHOOK",
  platform: "SLACK",
  authorization_header: "",
  authorization_key: "",
  is_active: false,
  max_retries: 0,
  notify_on_failures: false,
  delivery_mode: "IMMEDIATE",
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
  const [batchIntervalMinutes, setBatchIntervalMinutes] = useState(
    FALLBACK_BATCH_INTERVAL_MINUTES,
  );
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    // Read live org-scoped interval (UNS-611 v2). Fall back silently to the
    // hardcoded 30-min default — the dropdown still labels something useful.
    if (!sessionDetails?.orgId) {
      return;
    }
    axiosPrivate({
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails.orgId}/notifications/settings/`,
    })
      .then((res) => {
        const seconds = res?.data?.club_interval_seconds;
        if (typeof seconds === "number" && seconds > 0) {
          setBatchIntervalMinutes(Math.max(1, Math.round(seconds / 60)));
        }
      })
      .catch(() => {
        // Non-fatal — keep fallback.
      });
  }, [sessionDetails?.orgId]);

  const deliveryModes = [
    { value: "IMMEDIATE", label: "Immediate" },
    { value: "BATCHED", label: "Batched" },
  ];

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
    let nextValues = { ...formDetails, ...allValues };
    // Failure alerts must not be delayed by the batch window — auto-select
    // IMMEDIATE the moment the box is checked. The user can still override
    // to BATCHED afterward and that choice will stick.
    if (
      Object.hasOwn(changedValues, "notify_on_failures") &&
      changedValues.notify_on_failures === true
    ) {
      nextValues = { ...nextValues, delivery_mode: "IMMEDIATE" };
      form.setFieldsValue({ delivery_mode: "IMMEDIATE" });
    }
    setFormDetails(nextValues);
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

  const triggerSubmit = () => {
    const body = { ...formDetails };
    body[type] = id;

    if (editDetails) {
      handleUpdate(body, editDetails?.id);
    } else {
      handleSubmit(body);
    }
  };

  const handleAuthorizationTypeChange = (value) => {
    setFormDetails((prevDetails) => ({
      ...prevDetails,
      authorization_type: value,
      authorization_key: value === "NONE" ? "" : prevDetails.authorization_key,
      authorization_header:
        value === "CUSTOM_HEADER" ? prevDetails.authorization_header : "",
    }));
  };

  const formItems = [
    {
      label: "Name",
      name: "name",
      rules: [{ required: true, message: "Please enter name" }],
      component: <Input />,
    },
    {
      label: "URL",
      name: "url",
      rules: [{ required: true, message: "Please enter URL" }],
      component: <Input />,
      tooltip:
        "Provide the URL associated with this item. This field is required.",
    },
    {
      label: "Notification Type",
      name: "notification_type",
      component: <Select options={NOTIFICATION_TYPE_ITEMS} />,
      tooltip: "Select the type of notification you want to send.",
    },
    {
      label: "Platform",
      name: "platform",
      component: <Select options={PLATFORM_TYPES} />,
      tooltip: "Choose the platform where the notification will be used.",
    },
    {
      label: "Authorization Type",
      name: "authorization_type",
      component: (
        <Select
          options={AUTHORIZATION_TYPES}
          onChange={handleAuthorizationTypeChange}
        />
      ),
      tooltip:
        "Select the type of authorization required for this notification.",
    },
    {
      label: "Authorization Header",
      name: "authorization_header",
      component: <Input />,
      tooltip: "Enter the custom authorization header needed for requests.",
      rules:
        formDetails.authorization_type === "CUSTOM_HEADER"
          ? [{ required: true, message: "Authorization Header is required" }]
          : [],
      hidden: formDetails.authorization_type !== "CUSTOM_HEADER",
    },
    {
      label: "Authorization Key",
      name: "authorization_key",
      component: <Input />,
      tooltip:
        "Provide the authorization key used to validate the notification.",
      rules:
        formDetails.authorization_type !== "NONE"
          ? [{ required: true, message: "Authorization key is required" }]
          : [],
      hidden: formDetails.authorization_type === "NONE",
    },
    {
      label: "Max Retries",
      name: "max_retries",
      component: <Input type="number" />,
      tooltip:
        "Specify the maximum number of times the notification should be retried if it fails.",
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
      {formItems.map(
        ({ label, name, rules, component, tooltip, hidden }) =>
          !hidden && (
            <Form.Item
              key={name}
              label={label}
              name={name}
              rules={rules}
              tooltip={tooltip || ""}
              validateStatus={
                getBackendErrorDetail(name, backendErrors) ? "error" : ""
              }
              help={getBackendErrorDetail(name, backendErrors)}
            >
              {component}
            </Form.Item>
          ),
      )}
      <Form.Item
        name="notify_on_failures"
        valuePropName="checked"
        tooltip="When enabled, only runs with at least one failed file or a run-level error/stop trigger this notification. Otherwise notifications fire on every completion."
      >
        <Checkbox>Notify on failures only</Checkbox>
      </Form.Item>
      <Form.Item
        label="Delivery Mode"
        name="delivery_mode"
        tooltip="Immediate fires on every completion. Batched buffers events and dispatches a single clubbed message per webhook every batch interval."
        extra={
          formDetails.delivery_mode === "BATCHED"
            ? `Notifications will be batched and sent every ${batchIntervalMinutes} minutes. Org admins can change this in Platform Settings.`
            : null
        }
      >
        <Select options={deliveryModes} />
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
