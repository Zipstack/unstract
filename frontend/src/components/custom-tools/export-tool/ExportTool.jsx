import {
  DeleteOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  List,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import "./ExportTool.css";

import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

const SHARE_ALL = "share_all";
const SHARE_CUSTOM = "share_custom";

function ExportTool({
  open,
  setOpen,
  toolDetails,
  permissionEdit,
  loading,
  allUsers,
  onApply,
}) {
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [filteredUsers, setFilteredUsers] = useState([]);
  const [sharingOption, setSharingOption] = useState(SHARE_ALL);

  useEffect(() => {
    if (permissionEdit && toolDetails?.shared_users) {
      // set the selectedUsers to the IDs of shared users
      // filter owners and shared users

      const promptStudioUsers = toolDetails?.prompt_studio_users.map((user) =>
        user?.id?.toString()
      );

      const users = allUsers.filter((user) => {
        const userId = user?.id?.toString();
        return (
          !selectedUsers.includes(userId) &&
          !promptStudioUsers.includes(userId) &&
          toolDetails?.created_by?.toString() !== userId
        );
      });

      setFilteredUsers(users);
      toolDetails?.shared_to_org
        ? setSharingOption(SHARE_ALL)
        : setSharingOption(SHARE_CUSTOM);
    }
  }, [permissionEdit, toolDetails, allUsers, selectedUsers]);

  useEffect(() => {
    if (toolDetails?.shared_users) {
      setSelectedUsers(
        toolDetails.shared_users
          .filter((user) => {
            const promptStudioUsers = toolDetails?.prompt_studio_users.map(
              (user) => user?.id?.toString()
            );
            const userId = user?.id?.toString();
            return (
              !promptStudioUsers.includes(userId) &&
              toolDetails?.created_by?.toString() !== userId
            );
          })
          .map((user) => user?.id?.toString())
      );
    }
  }, [toolDetails, allUsers]);

  const handleDeleteUser = (userId) => {
    setSelectedUsers((prevSelectedUsers) =>
      prevSelectedUsers.filter((user) => user !== userId)
    );
  };
  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  const onChange = (e) => {
    setSharingOption(e.target.value);
  };

  let sharedWithContent;
  if (sharingOption === SHARE_ALL) {
    sharedWithContent = <Typography.Text>Shared with everyone</Typography.Text>;
  } else {
    sharedWithContent = (
      <>
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
          renderItem={(item) => (
            <List.Item
              extra={
                permissionEdit && (
                  <div onClick={(event) => event.stopPropagation()} role="none">
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
                    <Typography.Text className="export-username">
                      {item.email}
                    </Typography.Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
        <Typography>
          Exported Tools are always shared with the Prompt Studio projects owner
          and users in addition to other users it is explicitly shared with
        </Typography>
      </>
    );
  }

  return (
    toolDetails && (
      <Modal
        title={"Export settings"}
        open={open}
        onCancel={() => setOpen(false)}
        maskClosable={false}
        centered
        closable={true}
        okText={"Apply"}
        onOk={() =>
          onApply(selectedUsers, toolDetails, sharingOption === SHARE_ALL)
        }
        cancelButtonProps={!permissionEdit && { style: { display: "none" } }}
        okButtonProps={!permissionEdit && { style: { display: "none" } }}
        className="share-permission-modal"
      >
        {loading ? (
          <SpinnerLoader />
        ) : (
          <>
            {allUsers.length > 1 && (
              <Radio.Group
                onChange={onChange}
                value={sharingOption}
                className="export-per-radio"
              >
                <Radio value={SHARE_ALL}>Share with everyone</Radio>
                <Radio value={SHARE_CUSTOM}>Custom share</Radio>
              </Radio.Group>
            )}
            {permissionEdit && sharingOption !== SHARE_ALL && (
              <Select
                filterOption={filterOption}
                showSearch
                size={"middle"}
                placeholder="Search"
                value={null}
                className="export-permission-search"
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

ExportTool.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  toolDetails: PropTypes.object,
  permissionEdit: PropTypes.bool,
  loading: PropTypes.bool,
  allUsers: PropTypes.array,
  onApply: PropTypes.func,
};

export { ExportTool };
