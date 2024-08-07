import PropTypes from "prop-types";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { Button, Space, Switch, Table, Tooltip } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";

function DisplayNotifications({ setIsForm, rows }) {
  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Type",
      dataIndex: "notification_type",
      key: "notification_type",
    },
    {
      title: "Active",
      key: "is_active",
      dataIndex: "is_active",
      align: "center",
      render: (_, record) => <Switch size="small" checked={record.is_active} />,
    },
    {
      title: "Actions",
      key: "pipeline_id",
      align: "center",
      render: (_, record) => (
        <>
          <Space className="actions">
            <Tooltip title="edit" className="cursorPointer">
              <EditOutlined />
            </Tooltip>
          </Space>
          <Space className="actions">
            <Tooltip title="delete" className="cursorPointer">
              <DeleteOutlined />
            </Tooltip>
          </Space>
        </>
      ),
    },
  ];

  return (
    <SpaceWrapper>
      <div className="display-flex-right">
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => setIsForm(true)}
        >
          Create Notification
        </Button>
      </div>
      <Table columns={columns} dataSource={rows} />
    </SpaceWrapper>
  );
}

DisplayNotifications.propTypes = {
  setIsForm: PropTypes.func.isRequired,
  rows: PropTypes.array,
};

export { DisplayNotifications };
