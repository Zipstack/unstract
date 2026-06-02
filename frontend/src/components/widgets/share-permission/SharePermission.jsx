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
  TeamOutlined,
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
  allGroups = [],
  onApply,
  isSharableToOrg = false,
}) {
  const { sessionDetails } = useSessionStore();
  const currentUserId = sessionDetails?.id?.toString();
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState([]);
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
    if (adapter?.shared_groups) {
      setSelectedGroupIds(
        adapter.shared_groups.map((g) => (g?.id === undefined ? g : g.id)),
      );
    } else {
      setSelectedGroupIds([]);
    }
  }, [adapter, allUsers]);

  const handleDeleteUser = (userId) => {
    setSelectedUsers((prev) =>
      prev.filter((user) => String(user) !== String(userId)),
    );
  };

  const handleDeleteGroup = (groupId) => {
    setSelectedGroupIds((prev) => prev.filter((id) => id !== groupId));
  };

  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  const handleShareWithEveryone = (checked) => {
    setShareWithEveryone(checked);
  };

  const groupCandidateOptions = allGroups
    .filter((g) => !selectedGroupIds.includes(g.id))
    .map((g) => ({ label: g.name, value: g.id }));

  // Admins have org-wide access, so they aren't listed as explicit shares.
  // This also hides legacy admin rows created before the auto-share removal.
  const userItems = selectedUsers
    .map((userId) => {
      const user = allUsers.find((u) =>
        u?.id !== undefined
          ? u?.id.toString() === userId.toString()
          : u?.toString() === userId.toString(),
      );
      return {
        kind: "user",
        id: user?.id,
        email: user?.email,
        is_admin: user?.is_admin,
      };
    })
    .filter((user) => !user.is_admin);

  const groupItems = selectedGroupIds.map((groupId) => {
    const group = allGroups.find((g) => g.id === groupId);
    return {
      kind: "group",
      id: groupId,
      name: group?.name || `Group #${groupId}`,
    };
  });

  let sharedWithContent;
  if (shareWithEveryone) {
    sharedWithContent = <Typography.Text>Shared with everyone</Typography.Text>;
  } else if (userItems.length > 0 || groupItems.length > 0) {
    sharedWithContent = (
      <List
        dataSource={[...userItems, ...groupItems]}
        renderItem={(item) => (
          <List.Item
            extra={
              permissionEdit && (
                <Popconfirm
                  title="Revoke Access"
                  description={`Are you sure you want to revoke access to '${
                    item.kind === "user" ? item.email : item.name
                  }'?`}
                  okText="Yes"
                  cancelText="No"
                  icon={<QuestionCircleOutlined style={{ color: "#faad14" }} />}
                  onConfirm={() => {
                    if (item.kind === "user") {
                      handleDeleteUser(item.id);
                    } else {
                      handleDeleteGroup(item.id);
                    }
                  }}
                >
                  <Typography.Text>
                    <DeleteOutlined className="action-icon-buttons" />
                  </Typography.Text>
                </Popconfirm>
              )
            }
          >
            <List.Item.Meta
              title={
                <>
                  <Avatar
                    className="shared-user-avatar"
                    icon={
                      item.kind === "user" ? <UserOutlined /> : <TeamOutlined />
                    }
                  />
                  <Typography.Text className="shared-username">
                    {item.kind === "user" ? item.email : item.name}
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
        title="Share access"
        open={open}
        onCancel={() => setOpen(false)}
        maskClosable={false}
        centered
        closable={true}
        okText={"Apply"}
        onOk={() =>
          onApply(selectedUsers, adapter, shareWithEveryone, selectedGroupIds)
        }
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
              <>
                <div className="share-permission-section">
                  <Typography.Text strong>Add users</Typography.Text>
                  <Select
                    filterOption={filterOption}
                    showSearch
                    size={"middle"}
                    placeholder="Find a user by email"
                    value={null}
                    className="share-permission-search"
                    onChange={(selectedValue) => {
                      const isValueSelected =
                        selectedUsers.includes(selectedValue);
                      if (!isValueSelected) {
                        setSelectedUsers([...selectedUsers, selectedValue]);
                      }
                    }}
                    options={filteredUsers.map((user) => ({
                      label: user.email,
                      value: user.id,
                    }))}
                  />
                </div>
                {allGroups.length > 0 && (
                  <div className="share-permission-section">
                    <Typography.Text strong>Add groups</Typography.Text>
                    <Select
                      filterOption={filterOption}
                      showSearch
                      size={"middle"}
                      placeholder="Find a group by name"
                      value={null}
                      className="share-permission-search"
                      onChange={(groupId) => {
                        if (!selectedGroupIds.includes(groupId)) {
                          setSelectedGroupIds([...selectedGroupIds, groupId]);
                        }
                      }}
                      options={groupCandidateOptions}
                    />
                  </div>
                )}
              </>
            )}
            <div className="share-permission-section">
              <Typography.Text strong>Currently shared with</Typography.Text>
              {sharedWithContent}
            </div>
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
  allGroups: PropTypes.array,
  onApply: PropTypes.func,
  isSharableToOrg: PropTypes.bool,
};

export { SharePermission };
