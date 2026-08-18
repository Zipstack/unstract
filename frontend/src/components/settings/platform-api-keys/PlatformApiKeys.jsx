import { Form, Select, Tag } from "antd";

import { ApiKeyManager } from "../api-key-manager/ApiKeyManager.jsx";

const PERMISSION_OPTIONS = [
  { value: "read_write", label: "Read/Write", color: "blue" },
  { value: "read", label: "Read", color: "default" },
  { value: "full_access", label: "Full Access", color: "green" },
];
const PERMISSION_CONFIG = Object.fromEntries(
  PERMISSION_OPTIONS.map(({ value, label, color }) => [
    value,
    { label, color },
  ]),
);

const permissionColumn = {
  title: "Permission",
  dataIndex: "permission",
  key: "permission",
  width: "10%",
  render: (text) => {
    const { color, label } = PERMISSION_CONFIG[text] ?? {
      color: "default",
      label: `Unknown: ${text}`,
    };
    return <Tag color={color}>{label}</Tag>;
  },
};

function PlatformApiKeys() {
  return (
    <ApiKeyManager
      title="Platform API Keys"
      entityLabel="API Key"
      resourcePath="platform-api"
      extraColumns={[permissionColumn]}
      renderCreateFields={() => (
        <Form.Item
          name="permission"
          label="Permission"
          initialValue="read_write"
        >
          <Select options={PERMISSION_OPTIONS} />
        </Form.Item>
      )}
      renderEditFields={() => (
        <Form.Item name="permission" label="Permission">
          <Select options={PERMISSION_OPTIONS} />
        </Form.Item>
      )}
      getEditInitialValues={(record) => ({ permission: record?.permission })}
    />
  );
}

export { PlatformApiKeys };
