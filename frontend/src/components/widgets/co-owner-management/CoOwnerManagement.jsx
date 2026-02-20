import { Avatar, List, Modal, Popconfirm, Select, Typography } from "antd";
import PropTypes from "prop-types";
import {
  DeleteOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useMemo, useState } from "react";

import { SpinnerLoader } from "../spinner-loader/SpinnerLoader";
import "./CoOwnerManagement.css";

function CoOwnerManagement({
  open,
  setOpen,
  resourceId,
  resourceType,
  allUsers,
  coOwners,
  loading,
  onAddCoOwner,
  onRemoveCoOwner,
}) {
  const [adding, setAdding] = useState(false);
  const [removingUserId, setRemovingUserId] = useState(null);

  // co_owners is the single source of truth (creator is always in it)
  const ownersList = coOwners || [];
  const totalOwners = ownersList.length;

  // Users available for adding (exclude existing co-owners)
  const availableUsers = useMemo(() => {
    const coOwnerIds = (coOwners || []).map((u) => u?.id?.toString());
    return (allUsers || []).filter(
      (user) => !coOwnerIds.includes(user?.id?.toString())
    );
  }, [allUsers, coOwners]);

  const handleAdd = async (userId) => {
    setAdding(true);
    try {
      await onAddCoOwner(resourceId, userId);
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (userId) => {
    setRemovingUserId(userId);
    try {
      await onRemoveCoOwner(resourceId, userId);
    } finally {
      setRemovingUserId(null);
    }
  };

  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  return (
    <Modal
      title={`Manage Co-Owners - ${resourceType}`}
      open={open}
      onCancel={() => setOpen(false)}
      maskClosable={false}
      centered
      closable={true}
      footer={null}
      className="co-owner-modal"
    >
      {loading ? (
        <SpinnerLoader />
      ) : (
        <>
          <Select
            filterOption={filterOption}
            showSearch
            size="middle"
            placeholder="Add a co-owner..."
            value={null}
            className="co-owner-search"
            loading={adding}
            disabled={adding}
            onChange={(selectedValue) => handleAdd(selectedValue)}
            options={availableUsers.map((user) => ({
              label: user.email,
              value: user.id,
            }))}
          />
          <Typography.Title level={5}>Co-Owners</Typography.Title>
          {ownersList.length > 0 ? (
            <List
              dataSource={ownersList}
              renderItem={(item) => {
                return (
                  <List.Item
                    extra={
                      totalOwners > 1 && (
                        <div
                          onClick={(event) => event.stopPropagation()}
                          role="none"
                        >
                          <Popconfirm
                            key={`${item.id}-remove`}
                            title="Remove Co-Owner"
                            description={`Are you sure you want to remove '${
                              item?.username || item?.email
                            }' as co-owner?`}
                            okText="Yes"
                            cancelText="No"
                            icon={<QuestionCircleOutlined />}
                            onConfirm={() => handleRemove(item?.id)}
                          >
                            <Typography.Text>
                              <DeleteOutlined
                                className="action-icon-buttons"
                                style={{
                                  opacity:
                                    removingUserId === item?.id ? 0.4 : 1,
                                }}
                              />
                            </Typography.Text>
                          </Popconfirm>
                        </div>
                      )
                    }
                  >
                    <List.Item.Meta
                      title={
                        <>
                          <Avatar
                            className="shared-user-avatar"
                            icon={<UserOutlined />}
                          />
                          <Typography.Text className="shared-username">
                            {item.username || item.email}
                          </Typography.Text>
                        </>
                      }
                    />
                  </List.Item>
                );
              }}
            />
          ) : (
            <Typography>No co-owners yet</Typography>
          )}
        </>
      )}
    </Modal>
  );
}

CoOwnerManagement.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  resourceId: PropTypes.string.isRequired,
  resourceType: PropTypes.string.isRequired,
  allUsers: PropTypes.array,
  coOwners: PropTypes.array,
  loading: PropTypes.bool,
  onAddCoOwner: PropTypes.func.isRequired,
  onRemoveCoOwner: PropTypes.func.isRequired,
};

export { CoOwnerManagement };
