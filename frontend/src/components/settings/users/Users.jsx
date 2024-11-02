import {
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Modal, Space, Table, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Users.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { TopBar } from "../../widgets/top-bar/TopBar.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

function Users() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const [userList, setUserList] = useState([]);
  const [filteredUserList, setFilteredUserList] = useState(userList);
  const { setAlertDetails } = useAlertStore();
  const [open, setOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [selectedUserEmail, setSelectedUserEmail] = useState();
  const [isTableLoading, setIsTableLoading] = useState(false);

  const { Text } = Typography;

  const showModal = () => {
    setOpen(true);
  };
  const removeUser = (emailToRemove) => {
    const newUserList = userList.filter((user) => user.email !== emailToRemove);
    setUserList(newUserList);
  };

  const handleDelete = async () => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
      data: { emails: [selectedUserEmail?.email] },
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };
    setConfirmLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        setAlertDetails({
          type: "success",
          content: "User deleted successfully",
        });
        setConfirmLoading(false);
        setOpen(false);
        removeUser(selectedUserEmail.email);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to delete user"));
        setConfirmLoading(false);
        setOpen(false);
      });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const getAllUsers = async () => {
    try {
      setIsTableLoading(true);
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
      };
      const response = await axiosPrivate(requestOptions);
      const users = response?.data?.members || [];
      setUserList(
        users.map((user) => ({
          key: user.id,
          email: user.email,
          role: user.role,
        }))
      );
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to load"));
    } finally {
      setIsTableLoading(false);
    }
  };

  const actionItems = [
    {
      key: "1",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            navigate(`/${sessionDetails?.orgName}/users/edit`, {
              state: selectedUserEmail,
            })
          }
        >
          <div>
            <EditOutlined />
          </div>
          <div>
            <Typography.Text>Edit</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "2",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={showModal}
        >
          <div>
            <DeleteOutlined />
          </div>
          <div>
            <Typography.Text>Delete</Typography.Text>
          </div>
        </Space>
      ),
    },
  ];
  const columns = [
    {
      title: "Email",
      dataIndex: "email",
    },
    {
      title: "Role",
      dataIndex: "role",
    },
    {
      title: "Actions",
      align: "center",
      render: (_, record) => (
        <Dropdown
          menu={{ items: actionItems }}
          trigger={["click"]}
          placement="bottomLeft"
        >
          <EllipsisOutlined
            rotate={90}
            style={{ cursor: "pointer" }}
            onClick={() => setSelectedUserEmail(record)}
          />
        </Dropdown>
      ),
    },
  ];

  const handleInviteUsers = () => {
    navigate(`/${sessionDetails?.orgName}/users/invite`);

    try {
      setPostHogCustomEvent("intent_add_user", {
        info: "Clicked on '+ Invite User' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };
  useEffect(() => {
    getAllUsers();
  }, []);

  useEffect(() => {
    setFilteredUserList(userList);
  }, [userList]);

  return (
    <>
      <TopBar
        enableSearch={true}
        title="Manage Users"
        searchData={userList}
        setFilteredUserList={setFilteredUserList}
      >
        <CustomButton
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleInviteUsers}
        >
          Invite User
        </CustomButton>
        <Button
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={getAllUsers}
          className="user-reload-button"
        />
      </TopBar>
      <div className="user-bg-col">
        <IslandLayout>
          <div className="user-table">
            <Table
              columns={columns}
              dataSource={filteredUserList}
              size="small"
              loading={{
                indicator: <SpinnerLoader />,
                spinning: isTableLoading,
              }}
            />
          </div>
        </IslandLayout>
      </div>
      <Modal
        title="Delete User"
        open={open}
        onOk={handleDelete}
        confirmLoading={confirmLoading}
        onCancel={handleCancel}
        centered
        className="delete-user-modal"
      >
        <Typography>Are you sure you want to delete user id</Typography>
        <Text strong>{selectedUserEmail?.email}</Text>
      </Modal>
    </>
  );
}

export { Users };
