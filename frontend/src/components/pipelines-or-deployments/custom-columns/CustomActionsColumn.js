import { EllipsisOutlined } from "@ant-design/icons";
import { Dropdown } from "antd";

const customActionsColumn = ({ actionItems, setSelectedRow }) => {
  const column = {
    title: "Actions",
    key: "actions_id",
    align: "center",
    render: (_, record) => (
      <Dropdown
        menu={{ items: actionItems }}
        placement="bottomLeft"
        onOpenChange={() => setSelectedRow(record)}
      >
        <EllipsisOutlined rotate={90} style={{ cursor: "pointer" }} />
      </Dropdown>
    ),
  };

  return column;
};

export default customActionsColumn;
