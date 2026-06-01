import {
  Avatar,
  Checkbox,
  List,
  Modal,
  Popconfirm,
  Select,
  Typography,
} from "antd";
import "./SharePermission.css";
import {
  DeleteOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../spinner-loader/SpinnerLoader";

function SharePermission({
  open,
  setOpen,
  adapter,
  permissionEdit,
  loading,
  allUsers,
  onApply,
  isSharableToOrg = false,
}) {
  const { sessionDetails } = useSessionStore();
  const currentUserId = sessionDetails?.userId?.toString();
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [shareWithEveryone, setShareWithEveryone] = useState(false);

  useEffect(() => {
    if (permissionEdit && adapter && adapter?.shared_users) {
      const creatorId = (
        adapter?.created_by?.id ?? adapter?.created_by
      )?.toString();
      const users = allUsers.filter((user) => {
        const userId = user?.id?.toString();
        // Already-selected users shouldn't reappear as options
        if (selectedUsers.includes(userId)) {
          return false;
        }
        // Can't share a resource with yourself
        if (userId === currentUserId) {
          return false;
        }
        // Admins already have access to everything — sharing is a no-op
        if (user?.is_admin) {
          return false;
        }
        // The creator already owns it, unless we're sharing org-wide
        if (!isSharableToOrg && userId === creatorId) {
          return false;
        }
        return true;
      });
      setFilteredUsers(users);
      setShareWithEveryone(adapter?.shared_to_org || false);
    }
  }, [
    permissionEdit,
    adapter,
    allUsers,
    selectedUsers,
    currentUserId,
    isSharableToOrg,
  ]);

  useEffect(() => {
    if (adapter?.shared_users) {
      setSelectedUsers(
        adapter.shared_users.map((user) => {
          if (user?.id !== undefined) {
            return user.id.toString();
          } else {
            return user?.toString();
          }
        }),
      );
    }
  }, [adapter, allUsers]);

  const handleDeleteUser = (userId) => {
    setSelectedUsers((prevSelectedUsers) =>
      prevSelectedUsers.filter((user) => user !== userId),
    );
  };
  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  const handleShareWithEveryone = (checked) => {
    setShareWithEveryone(checked);
  };

  let sharedWithContent;
  if (shareWithEveryone) {
    sharedWithContent = <Typography.Text>Shared with everyone</Typography.Text>;
  } else if (selectedUsers.length > 0) {
    sharedWithContent = (
      <List
        dataSource={selectedUsers.map((userId) => {
          const user = allUsers.find((u) => {
            if (u?.id !== undefined) {
              return u?.id.toString() === userId.toString();
            } else {
              return u?.toString() === userId.toString();
            }
          });
          return {
            id: user?.id,
            email: user?.email,
          };
        })}
        renderItem={(item) => (
          <List.Item
            extra={
              permissionEdit && (
                <div onClick={(event) => event.stopPropagation()} role="none">
                  <Popconfirm
                    key={`${item.id}-delete`}
                    title="Revoke Access"
                    description={`Are you sure you want to revoke access to '${item?.email}'?`}
                    okText="Yes"
                    cancelText="No"
                    icon={<QuestionCircleOutlined />}
                    onConfirm={(event) => handleDeleteUser(item?.id)}
                  >
                    <Typography.Text>
                      <DeleteOutlined className="action-icon-buttons" />
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
                    {item.email}
                  </Typography.Text>
                </>
              }
            />
          </List.Item>
        )}
      />
    );
  } else {
    sharedWithContent = <Typography>Not shared with anyone yet</Typography>;
  }

  return (
    adapter && (
      <Modal
        title={"Share Users"}
        open={open}
        onCancel={() => setOpen(false)}
        maskClosable={false}
        centered
        closable={true}
        okText={"Apply"}
        onOk={() => onApply(selectedUsers, adapter, shareWithEveryone)}
        cancelButtonProps={!permissionEdit && { style: { display: "none" } }}
        okButtonProps={!permissionEdit && { style: { display: "none" } }}
        className="share-permission-modal"
      >
        {loading ? (
          <SpinnerLoader />
        ) : (
          <>
            {isSharableToOrg && allUsers.length > 1 && (
              <Checkbox
                checked={shareWithEveryone}
                onChange={(e) => handleShareWithEveryone(e.target.checked)}
                className="share-per-checkbox"
                disabled={!permissionEdit}
              >
                Share with everyone in current org
              </Checkbox>
            )}
            {permissionEdit && !shareWithEveryone && (
              <Select
                filterOption={filterOption}
                showSearch
                size={"middle"}
                placeholder="Search"
                value={null}
                className="share-permission-search"
                onChange={(selectedValue) => {
                  const isValueSelected = selectedUsers.includes(selectedValue);
                  if (!isValueSelected) {
                    // Update the state only if the selected value is not already present
                    setSelectedUsers([...selectedUsers, selectedValue]);
                  }
                }}
                options={filteredUsers.map((user) => ({
                  label: user.email,
                  value: user.id,
                }))}
              >
                {filteredUsers.map((user) => {
                  return (
                    <Select.Option key={user?.id} value={user?.id}>
                      {user?.email}
                    </Select.Option>
                  );
                })}
              </Select>
            )}
            <Typography.Title level={5}>Shared with</Typography.Title>
            {sharedWithContent}
          </>
        )}
      </Modal>
    )
  );
}

SharePermission.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  adapter: PropTypes.object,
  permissionEdit: PropTypes.bool,
  loading: PropTypes.bool,
  allUsers: PropTypes.array,
  onApply: PropTypes.func,
  isSharableToOrg: PropTypes.bool,
};

export { SharePermission };
