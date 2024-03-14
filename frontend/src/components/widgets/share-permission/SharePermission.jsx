import { Avatar, List, Modal, Popconfirm, Select, Typography } from "antd";
import "./SharePermission.css";
import PropTypes from "prop-types";
import {
  DeleteOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { SpinnerLoader } from "../spinner-loader/SpinnerLoader";
import { useEffect, useState } from "react";

function SharePermission({
  open,
  setOpen,
  adapter,
  permissionEdit,
  loading,
  allUsers,
  onApply,
}) {
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);

  useEffect(() => {
    if (permissionEdit && adapter && adapter.shared_users) {
      // If permissionEdit is true, and adapter is available,
      // set the selectedUsers to the IDs of shared users
      const users = allUsers.filter((user) => {
        if (adapter?.created_by?.id !== undefined) {
          return (
            user.id !== adapter?.created_by?.id?.toString() &&
            !selectedUsers.includes(user.id.toString())
          );
        } else {
          return (
            user.id !== adapter?.created_by?.toString() &&
            !selectedUsers.includes(user.id.toString())
          );
        }
      });
      setFilteredUsers(users);
    }
  }, [permissionEdit, adapter, allUsers, selectedUsers]);

  useEffect(() => {
    if (adapter && adapter.shared_users) {
      setSelectedUsers(
        adapter.shared_users.map((user) => {
          if (user?.id !== undefined) {
            return user.id.toString();
          } else {
            return user.toString();
          }
        })
      );
    }
  }, [adapter, allUsers]);

  const handleDeleteUser = (userId) => {
    setSelectedUsers((prevSelectedUsers) =>
      prevSelectedUsers.filter((user) => user !== userId)
    );
  };

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
        onOk={() => onApply(selectedUsers, adapter)}
        cancelButtonProps={!permissionEdit && { style: { display: "none" } }}
        okButtonProps={!permissionEdit && { style: { display: "none" } }}
        className="share-permission-modal"
      >
        {loading ? (
          <SpinnerLoader />
        ) : (
          <>
            {permissionEdit ? (
              <Select
                showSearch
                size={"middle"}
                placeholder="Search"
                value={null}
                onChange={(selectedValue) => {
                  const isValueSelected = selectedUsers.includes(selectedValue);
                  if (!isValueSelected) {
                    // Update the state only if the selected value is not already present
                    setSelectedUsers([...selectedUsers, selectedValue]);
                  }
                }}
                style={{ width: "100%" }}
                options={filteredUsers.map((user) => ({
                  label: user.email,
                  value: user.id,
                }))}
                onSearch={(searchValue) =>
                  setFilteredUsers(
                    allUsers.filter((user) =>
                      user.email
                        .toLowerCase()
                        .includes(searchValue.toLowerCase())
                    )
                  )
                }
              >
                {filteredUsers.map((user) => (
                  <Select.Option key={user.id} value={user.id}>
                    {user.email}
                  </Select.Option>
                ))}
              </Select>
            ) : (
              <>
                <Typography.Title level={5}>Owned By</Typography.Title>
                <List
                  dataSource={[adapter.created_by]}
                  renderItem={(item) => {
                    return (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <>
                              <Avatar
                                className="shared-user-avatar"
                                icon={<UserOutlined />}
                              />
                              <Typography.Text className="shared-username">
                                {item?.username || item}
                              </Typography.Text>
                            </>
                          }
                        />
                      </List.Item>
                    );
                  }}
                />
              </>
            )}
            <Typography.Title level={5}>Shared with</Typography.Title>
            {selectedUsers.length > 0 ? (
              <List
                dataSource={selectedUsers.map((userId) => {
                  const user = allUsers.find(
                    (u) => u.id.toString() === userId.toString()
                  );
                  return {
                    id: user.id,
                    email: user.email,
                  };
                })}
                renderItem={(item) => {
                  return (
                    <List.Item
                      extra={
                        permissionEdit && (
                          <div
                            onClick={(event) => event.stopPropagation()}
                            role="none"
                          >
                            <Popconfirm
                              key={`${item.id}-delete`}
                              title="Delete the tool"
                              description="Are you sure to remove this user?"
                              okText="Yes"
                              cancelText="No"
                              icon={<QuestionCircleOutlined />}
                              onConfirm={(event) => handleDeleteUser(item.id)}
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
                  );
                }}
              />
            ) : (
              <Typography>Not shared with anyone yet</Typography>
            )}
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
};

export { SharePermission };
