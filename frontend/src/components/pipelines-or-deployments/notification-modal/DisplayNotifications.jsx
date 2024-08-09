import PropTypes from "prop-types";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { Button, Space, Switch, Table, Tooltip } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";

function DisplayNotifications({
  setIsForm,
  rows,
  isLoading,
  updateStatus,
  handleDelete,
  setEditDetails,
}) {
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
      render: (_, record) => (
        <Switch
          size="small"
          defaultChecked={record?.is_active}
          onChange={() => updateStatus(record)}
        />
      ),
    },
    {
      title: "Actions",
      key: "pipeline_id",
      align: "center",
      render: (_, record) => (
        <>
          <Space className="actions">
            <Tooltip title="edit" className="cursorPointer">
              <Button
                type="text"
                size="small"
                onClick={() => handleEdit(record)}
              >
                <EditOutlined />
              </Button>
            </Tooltip>
          </Space>
          <Space className="actions">
            <Tooltip title="delete" className="cursorPointer">
              <ConfirmModal
                handleConfirm={() => handleDelete(record?.id, record?.name)}
                content="Are you sure you want to delete?"
              >
                <Button type="text" size="small">
                  <DeleteOutlined />
                </Button>
              </ConfirmModal>
            </Tooltip>
          </Space>
        </>
      ),
    },
  ];

  const handleEdit = (record) => {
    setIsForm(true);
    setEditDetails(record);
  };

  return (
    <SpaceWrapper>
      <div className="display-flex-right">
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setIsForm(true)}
        >
          Create Notification
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={rows}
        loading={{
          indicator: <SpinnerLoader />,
          spinning: isLoading,
        }}
        pagination={{ pageSize: 5 }}
      />
    </SpaceWrapper>
  );
}

DisplayNotifications.propTypes = {
  setIsForm: PropTypes.func.isRequired,
  rows: PropTypes.array,
  isLoading: PropTypes.bool.isRequired,
  updateStatus: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  setEditDetails: PropTypes.func.isRequired,
};

export { DisplayNotifications };
