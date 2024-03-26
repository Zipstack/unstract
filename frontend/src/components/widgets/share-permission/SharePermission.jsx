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
  isSharableToOrg = false,
}) {
  const [selectedUsers, setSelectedUsers] = useState([]);
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
    if (adapter && adapter?.shared_users) {
      setSelectedUsers(
        adapter.shared_users.map((user) => {
          if (user?.id !== undefined) {
            return user.id.toString();
          } else {
            return user?.toString();
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
  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  const handleShareWithEveryone = (checked) => {
    setShareWithEveryone(checked);
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
              >
                Share with everyone
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
            {shareWithEveryone ? (
              <Typography.Text>Shared with everyone</Typography.Text>
            ) : selectedUsers.length > 0 ? (
              <List
                dataSource={selectedUsers.map((userId) => {
                  const user = allUsers.find(
                    (u) => u?.id.toString() === userId.toString()
                  );
                  return {
                    id: user?.id,
                    email: user?.email,
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
                              title="Delete the User"
                              description={`Are you sure to remove ${item?.email}?`}
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
  isSharableToOrg: PropTypes.bool,
};

export { SharePermission };
