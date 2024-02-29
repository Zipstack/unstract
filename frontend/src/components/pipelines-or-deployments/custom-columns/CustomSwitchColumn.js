import { Switch } from "antd";

const customSwitchColumn = ({ updateStatus }) => {
  const column = {
    title: "Enabled",
    key: "active",
    dataIndex: "active",
    align: "center",
    render: (_, record) => (
      <Switch
        size="small"
        checked={record.is_active}
        onChange={(e) => {
          updateStatus(record);
        }}
      />
    ),
  };

  return column;
};

export default customSwitchColumn;
