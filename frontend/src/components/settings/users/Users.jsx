import { Ellipsis, Pencil, Plus, RotateCw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Dropdown, Modal } from "@/components/ui/shims/antd-overlays";
import { Table } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";
import "./Users.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { TopBar } from "../../widgets/top-bar/TopBar.jsx";

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
        })),
      );
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to load"));
    } finally {
      setIsTableLoading(false);
    }
  };

  const isSsoLocalAuthz =
    !!sessionDetails?.provider && !!sessionDetails?.disableSsoIdpAuthorization;

  /*
   * The row each entry acts on is bound HERE, in the render closure, rather
   * than recorded by an onClick on the kebab itself. The menu opens on
   * pointerdown and then pins `pointer-events: none` on <body> while it is
   * open, so the click that would have followed on the kebab never lands: the
   * row stayed unrecorded, Edit navigated to /users/edit with no state, and
   * the page bounced to the dashboard. The Delete modal named no user for the
   * same reason.
   */
  const getActionItems = (record) => {
    const editItem = {
      key: "1",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            navigate(`/${sessionDetails?.orgName}/users/edit`, {
              state: record,
            })
          }
        >
          <div>
            <Pencil />
          </div>
          <div>
            <Typography.Text>Edit</Typography.Text>
          </div>
        </Space>
      ),
    };

    const deleteItem = {
      key: "2",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => {
            setSelectedUserEmail(record);
            showModal();
          }}
        >
          <div>
            <Trash2 />
          </div>
          <div>
            <Typography.Text>Delete</Typography.Text>
          </div>
        </Space>
      ),
    };

    return isSsoLocalAuthz ? [editItem] : [editItem, deleteItem];
  };

  const baseColumns = [
    {
      title: "Email",
      dataIndex: "email",
    },
    {
      title: "Role",
      dataIndex: "role",
    },
  ];

  const actionColumn = {
    title: "Actions",
    align: "center",
    render: (_, record) => (
      <Dropdown
        menu={{ items: getActionItems(record) }}
        trigger={["click"]}
        placement="bottomLeft"
      >
        <Ellipsis rotate={90} style={{ cursor: "pointer" }} />
      </Dropdown>
    ),
  };

  const columns =
    !sessionDetails?.provider || isSsoLocalAuthz
      ? [...baseColumns, actionColumn]
      : baseColumns;

  const handleInviteUsers = () => {
    navigate(`/${sessionDetails?.orgName}/users/invite`);

    try {
      setPostHogCustomEvent("intent_add_user", {
        info: "Clicked on '+ Invite User' button",
      });
    } catch (_err) {
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
        {!sessionDetails?.provider && (
          <CustomButton
            type="primary"
            icon={<Plus />}
            onClick={handleInviteUsers}
          >
            Invite User
          </CustomButton>
        )}
        <Button
          shape="circle"
          icon={<RotateCw />}
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
