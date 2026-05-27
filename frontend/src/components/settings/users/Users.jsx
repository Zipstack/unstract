import {
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Dropdown,
  Modal,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Users.css";

import { formattedDateTime } from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { TopBar } from "../../widgets/top-bar/TopBar.jsx";

const MEMBERS_TAB = "members";
const INVITATIONS_TAB = "invitations";

function Users() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const [userList, setUserList] = useState([]);
  const [filteredUserList, setFilteredUserList] = useState([]);
  const [invitationList, setInvitationList] = useState([]);
  const [filteredInvitationList, setFilteredInvitationList] = useState([]);
  const { setAlertDetails } = useAlertStore();
  const [open, setOpen] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [selectedUserEmail, setSelectedUserEmail] = useState();
  const [selectedInvitation, setSelectedInvitation] = useState();
  const [invitationDeleteOpen, setInvitationDeleteOpen] = useState(false);
  const [invitationDeleteLoading, setInvitationDeleteLoading] = useState(false);
  const [isTableLoading, setIsTableLoading] = useState(false);
  const [isInvitationsLoading, setIsInvitationsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState(MEMBERS_TAB);

  const { Text } = Typography;

  const showModal = () => {
    setOpen(true);
  };
  const removeUser = (emailToRemove) => {
    const newUserList = userList.filter((user) => user.email !== emailToRemove);
    setUserList(newUserList);
  };

  const removeInvitation = (idToRemove) => {
    setInvitationList((prev) =>
      prev.filter((invitation) => invitation.id !== idToRemove),
    );
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
      .then(() => {
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

  const handleInvitationDeleteCancel = () => {
    setInvitationDeleteOpen(false);
  };

  const handleInvitationDelete = async () => {
    if (!selectedInvitation?.id) {
      return;
    }
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/invitation/${selectedInvitation.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
    };
    setInvitationDeleteLoading(true);
    axiosPrivate(requestOptions)
      .then(() => {
        removeInvitation(selectedInvitation.id);
        setAlertDetails({
          type: "success",
          content: "Invitation revoked",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to revoke invitation"));
      })
      .finally(() => {
        setInvitationDeleteLoading(false);
        setInvitationDeleteOpen(false);
      });
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

  const getAllInvitations = async () => {
    try {
      setIsInvitationsLoading(true);
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/invitation/`,
      };
      const response = await axiosPrivate(requestOptions);
      const invitations = response?.data?.members || [];
      setInvitationList(
        invitations.map((invitation) => ({
          key: invitation.id,
          id: invitation.id,
          email: invitation.email,
          roles: invitation.roles || [],
          inviter_name: invitation.inviter_name,
          created_at: invitation.created_at,
          expires_at: invitation.expires_at,
        })),
      );
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to load invitations"));
    } finally {
      setIsInvitationsLoading(false);
    }
  };

  const isSsoLocalAuthz =
    !!sessionDetails?.provider && !!sessionDetails?.disableSsoIdpAuthorization;

  const editItem = {
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
  };

  const deleteItem = {
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
  };

  const actionItems = isSsoLocalAuthz ? [editItem] : [editItem, deleteItem];

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
  };

  const columns =
    !sessionDetails?.provider || isSsoLocalAuthz
      ? [...baseColumns, actionColumn]
      : baseColumns;

  const formatRoleLabel = (name) =>
    typeof name === "string"
      ? name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      : name;

  const isExpired = (expiresAt) => {
    if (!expiresAt) {
      return false;
    }
    const expiry = new Date(expiresAt).getTime();
    return Number.isFinite(expiry) && expiry < Date.now();
  };

  const invitationColumns = [
    {
      title: "Email",
      dataIndex: "email",
    },
    {
      title: "Role",
      dataIndex: "roles",
      render: (roles) => {
        if (!roles?.length) {
          return "-";
        }
        return (
          <Space size={4} wrap>
            {roles.map((role) => (
              <Tag key={role}>{formatRoleLabel(role)}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: "Invited By",
      dataIndex: "inviter_name",
      render: (value) => value || "-",
    },
    {
      title: "Invited On",
      dataIndex: "created_at",
      render: (value) => formattedDateTime(value) || "-",
    },
    {
      title: "Expires On",
      dataIndex: "expires_at",
      render: (value) => formattedDateTime(value) || "-",
    },
    {
      title: "Status",
      dataIndex: "expires_at",
      render: (value) =>
        isExpired(value) ? (
          <Tag color="red">Expired</Tag>
        ) : (
          <Tag color="gold">Pending</Tag>
        ),
    },
    {
      title: "Actions",
      align: "center",
      render: (_, record) => (
        <Button
          type="text"
          icon={<DeleteOutlined />}
          onClick={() => {
            setSelectedInvitation(record);
            setInvitationDeleteOpen(true);
          }}
        />
      ),
    },
  ];

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

  const handleReload = () => {
    if (activeTab === INVITATIONS_TAB) {
      getAllInvitations();
    } else {
      getAllUsers();
    }
  };

  useEffect(() => {
    getAllUsers();
  }, []);

  useEffect(() => {
    if (activeTab === INVITATIONS_TAB && invitationList.length === 0) {
      getAllInvitations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  useEffect(() => {
    setFilteredUserList(userList);
  }, [userList]);

  useEffect(() => {
    setFilteredInvitationList(invitationList);
  }, [invitationList]);

  const isInvitationsTab = activeTab === INVITATIONS_TAB;
  const searchData = isInvitationsTab ? invitationList : userList;
  const setFilteredData = isInvitationsTab
    ? setFilteredInvitationList
    : setFilteredUserList;

  const tabItems = useMemo(
    () => [
      {
        key: MEMBERS_TAB,
        label: "Members",
        children: (
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
        ),
      },
      {
        key: INVITATIONS_TAB,
        label: "Invitations",
        children: (
          <div className="user-table">
            <Table
              columns={invitationColumns}
              dataSource={filteredInvitationList}
              size="small"
              loading={{
                indicator: <SpinnerLoader />,
                spinning: isInvitationsLoading,
              }}
            />
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      filteredUserList,
      filteredInvitationList,
      isTableLoading,
      isInvitationsLoading,
      columns,
    ],
  );

  return (
    <>
      <TopBar
        enableSearch={true}
        title="Manage Users"
        searchData={searchData}
        setFilteredUserList={setFilteredData}
      >
        {!sessionDetails?.provider && (
          <CustomButton
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleInviteUsers}
          >
            Invite User
          </CustomButton>
        )}
        <Button
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={handleReload}
          loading={
            activeTab === INVITATIONS_TAB
              ? isInvitationsLoading
              : isTableLoading
          }
          className="user-reload-button"
        />
      </TopBar>
      <div className="user-bg-col">
        <IslandLayout>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            className="user-tabs"
          />
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
      <Modal
        title="Revoke Invitation"
        open={invitationDeleteOpen}
        onOk={handleInvitationDelete}
        confirmLoading={invitationDeleteLoading}
        onCancel={handleInvitationDeleteCancel}
        okText="Revoke"
        okButtonProps={{ danger: true }}
        centered
        className="delete-user-modal"
      >
        <Typography>
          Are you sure you want to revoke the invitation for
        </Typography>
        <Text strong>{selectedInvitation?.email}</Text>
      </Modal>
    </>
  );
}

export { Users };
