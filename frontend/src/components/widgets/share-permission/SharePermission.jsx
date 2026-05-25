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
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [shareWithEveryone, setShareWithEveryone] = useState(false);

  useEffect(() => {
    if (permissionEdit && adapter && adapter?.shared_users) {
      // If permissionEdit is true, and adapter is available,
      // set the selectedUsers to the IDs of shared users
      const users = allUsers.filter((user) => {
        if (adapter?.created_by?.id !== undefined) {
          return isSharableToOrg
            ? !selectedUsers.includes(user?.id?.toString())
            : user?.id !== adapter?.created_by?.id?.toString() &&
                !selectedUsers.includes(user?.id?.toString());
        } else {
          return isSharableToOrg
            ? !selectedUsers.includes(user?.id?.toString())
            : user?.id !== adapter?.created_by?.toString() &&
                !selectedUsers.includes(user?.id?.toString());
        }
      });
      setFilteredUsers(users);
      setShareWithEveryone(adapter?.shared_to_org || false);
    }
  }, [permissionEdit, adapter, allUsers, selectedUsers]);

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
    setSelectedUsers((prev) => prev.filter((user) => user !== userId));
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

  let sharedWithContent;
  if (shareWithEveryone) {
    sharedWithContent = <Typography.Text>Shared with everyone</Typography.Text>;
  } else if (selectedUsers.length > 0 || selectedGroupIds.length > 0) {
    const userItems = selectedUsers.map((userId) => {
      const user = allUsers.find((u) => {
        if (u?.id !== undefined) {
          return u?.id.toString() === userId.toString();
        }
        return u?.toString() === userId.toString();
      });
      return {
        kind: "user",
        id: user?.id,
        email: user?.email,
      };
    });
    const groupItems = selectedGroupIds.map((groupId) => {
      const group = allGroups.find((g) => g.id === groupId);
      return {
        kind: "group",
        id: groupId,
        name: group?.name || `Group #${groupId}`,
      };
    });
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
