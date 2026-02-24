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
  const [pendingAdds, setPendingAdds] = useState([]);
  const [removingUserId, setRemovingUserId] = useState(null);
  const [applying, setApplying] = useState(false);

  const ownersList = coOwners || [];
  const totalOwners = ownersList.length;

  // Exclude both existing co-owners and pending adds from dropdown
  const availableUsers = useMemo(() => {
    const coOwnerIds = (coOwners || []).map((u) => u?.id?.toString());
    const pendingIds = pendingAdds.map((u) => u?.id?.toString());
    return (allUsers || []).filter(
      (user) =>
        !coOwnerIds.includes(user?.id?.toString()) &&
        !pendingIds.includes(user?.id?.toString())
    );
  }, [allUsers, coOwners, pendingAdds]);

  const handleSelect = (userId) => {
    const user = (allUsers || []).find(
      (u) => u?.id?.toString() === userId?.toString()
    );
    if (user) {
      setPendingAdds((prev) => [...prev, user]);
    }
  };

  const handleRemovePending = (userId) => {
    setPendingAdds((prev) =>
      prev.filter((u) => u?.id?.toString() !== userId?.toString())
    );
  };

  const handleRemoveExisting = async (userId) => {
    setRemovingUserId(userId);
    try {
      await onRemoveCoOwner(resourceId, userId);
    } finally {
      setRemovingUserId(null);
    }
  };

  const handleApply = async () => {
    const usersToAdd = [...pendingAdds];
    setApplying(true);
    try {
      for (const user of usersToAdd) {
        await onAddCoOwner(resourceId, user.id);
      }
    } finally {
      setPendingAdds([]);
      setApplying(false);
    }
  };

  const handleCancel = () => {
    setPendingAdds([]);
    setOpen(false);
  };

  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  const combinedList = [
    ...ownersList,
    ...pendingAdds.filter(
      (pending) =>
        !ownersList.some(
          (owner) => owner?.id?.toString() === pending?.id?.toString()
        )
    ),
  ];

  return (
    <Modal
      title={`Manage Co-Owners - ${resourceType}`}
      open={open}
      onCancel={handleCancel}
      onOk={handleApply}
      okText={"Apply"}
      confirmLoading={applying}
      maskClosable={false}
      centered
      closable={true}
      className="co-owner-modal"
    >
      {loading || applying ? (
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
            onChange={(selectedValue) => handleSelect(selectedValue)}
            options={availableUsers.map((user) => ({
              label: user.email,
              value: user.id,
            }))}
          />
          <Typography.Title level={5}>Co-Owners</Typography.Title>
          {combinedList.length > 0 ? (
            <List
              dataSource={combinedList}
              renderItem={(item) => {
                const isPending = pendingAdds.some(
                  (u) => u?.id?.toString() === item?.id?.toString()
                );
                return (
                  <List.Item
                    extra={
                      isPending ? (
                        <Typography.Text>
                          <DeleteOutlined
                            className="action-icon-buttons"
                            onClick={() => handleRemovePending(item?.id)}
                          />
                        </Typography.Text>
                      ) : (
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
                              onConfirm={() => handleRemoveExisting(item?.id)}
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
