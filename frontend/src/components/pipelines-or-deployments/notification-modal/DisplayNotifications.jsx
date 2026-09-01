import { Pencil, Plus, Trash2 } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Switch } from "@/components/ui/shims/antd-inputs";
import { Space } from "@/components/ui/shims/antd-layout";
import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { Table } from "@/components/ui/shims/antd-structure";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

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
        <Space>
          <Tooltip title="edit" className="cursorPointer">
            <Button
              type="text"
              size="small"
              icon={<Pencil />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip title="delete" className="cursorPointer">
            <ConfirmModal
              handleConfirm={() => handleDelete(record?.id, record?.name)}
              content="Are you sure you want to delete?"
            >
              <Button type="text" size="small" icon={<Trash2 />} />
            </ConfirmModal>
          </Tooltip>
        </Space>
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
        <Button type="primary" icon={<Plus />} onClick={() => setIsForm(true)}>
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
        pagination={false}
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
