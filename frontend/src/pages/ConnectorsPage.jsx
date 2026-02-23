import { useState, useEffect, useCallback } from "react";
import { Button } from "antd";
import { PlusOutlined } from "@ant-design/icons";

import { useAxiosPrivate } from "../hooks/useAxiosPrivate";
import { useSessionStore } from "../store/session-store";
import { useAlertStore } from "../store/alert-store";
import { useExceptionHandler } from "../hooks/useExceptionHandler";
import useRequestUrl from "../hooks/useRequestUrl";
import { useListSearch } from "../hooks/useListSearch";
import "./ConnectorsPage.css";
import { ToolNavBar } from "../components/navigations/tool-nav-bar/ToolNavBar";
import { ViewTools } from "../components/custom-tools/view-tools/ViewTools";
import { SharePermission } from "../components/widgets/share-permission/SharePermission";
import { CoOwnerManagement } from "../components/widgets/co-owner-management/CoOwnerManagement";
import { AddSourceModal } from "../components/input-output/add-source-modal/AddSourceModal";

function ConnectorsPage() {
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConnector, setEditingConnector] = useState(null);
  const [shareModalVisible, setShareModalVisible] = useState(false);
  const [sharingConnector, setSharingConnector] = useState(null);
  const [userList, setUserList] = useState([]);
  const [isPermissionEdit, setIsPermissionEdit] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [coOwnerOpen, setCoOwnerOpen] = useState(false);
  const [coOwnerData, setCoOwnerData] = useState({
    coOwners: [],
    createdBy: null,
  });
  const [coOwnerLoading, setCoOwnerLoading] = useState(false);
  const [coOwnerAllUsers, setCoOwnerAllUsers] = useState([]);
  const [coOwnerResourceId, setCoOwnerResourceId] = useState(null);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();
  const { displayList, setDisplayList, setMasterList, onSearch } =
    useListSearch("connector_name");

  useEffect(() => {
    fetchConnectors();
    fetchUsers();
  }, []);

  const fetchConnectors = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(getUrl("connector/"));
      setMasterList(response.data || []);
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to load connectors"));
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await axiosPrivate.get(getUrl("users/"));
      const users = response?.data?.members || [];
      setUserList(
        users
          .filter((user) => user?.id !== sessionDetails?.id)
          .map((user) => ({
            id: user?.id,
            email: user?.email,
          }))
      );
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to load users"));
    }
  };

  const handleCreateConnector = () => {
    setEditingConnector(null);
    setModalVisible(true);
  };

  const handleEditConnector = (_event, connector) => {
    setEditingConnector(connector);
    setModalVisible(true);
  };

  const handleDeleteConnector = async (_event, connector) => {
    try {
      await axiosPrivate.delete(getUrl(`connector/${connector.id}/`), {
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
        },
      });
      setAlertDetails({
        type: "success",
        content: "Connector deleted successfully",
      });
      fetchConnectors();
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to delete connector"));
    }
  };

  const handleShareConnector = async (_event, connector, isEdit) => {
    setIsShareLoading(true);
    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        axiosPrivate.get(getUrl("users/")),
        axiosPrivate.get(getUrl(`connector/users/${connector.id}/`), {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
      ]);

      const users =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      setUserList(users);
      setSharingConnector(sharedUsersResponse?.data);
      setIsPermissionEdit(isEdit);
      setShareModalVisible(true);
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to load sharing data"));
    } finally {
      setIsShareLoading(false);
    }
  };

  const handleShareSave = async (userIds, connector, shareWithEveryone) => {
    setIsShareLoading(true);
    try {
      const updateData = {
        shared_users: userIds,
        shared_to_org: shareWithEveryone || false,
      };

      await axiosPrivate.patch(
        getUrl(`connector/${connector.id}/`),
        updateData,
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        }
      );
      setShareModalVisible(false);
      setAlertDetails({
        type: "success",
        content: "Connector sharing updated successfully",
      });
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to update sharing"));
    } finally {
      setIsShareLoading(false);
    }
  };

  const handleCoOwner = async (_event, connector) => {
    setCoOwnerResourceId(connector.id);
    setCoOwnerLoading(true);
    setCoOwnerOpen(true);

    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        axiosPrivate.get(getUrl("users/")),
        axiosPrivate.get(getUrl(`connector/users/${connector.id}/`), {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
      ]);

      const users =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      setCoOwnerAllUsers(users);
      setCoOwnerData({
        coOwners: sharedUsersResponse.data?.co_owners || [],
        createdBy: sharedUsersResponse.data?.created_by || null,
      });
    } catch (err) {
      setAlertDetails(
        handleException(err, "Unable to fetch co-owner information")
      );
      setCoOwnerOpen(false);
    } finally {
      setCoOwnerLoading(false);
    }
  };

  const refreshCoOwnerData = async (resourceId) => {
    try {
      const res = await axiosPrivate.get(
        getUrl(`connector/users/${resourceId}/`),
        {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }
      );
      setCoOwnerData({
        coOwners: res.data?.co_owners || [],
        createdBy: res.data?.created_by || null,
      });
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to refresh co-owner data"));
    }
  };

  const onAddCoOwner = async (resourceId, userId) => {
    try {
      await axiosPrivate.post(
        getUrl(`connector/${resourceId}/owners/`),
        { user_id: userId },
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
        }
      );
      setAlertDetails({
        type: "success",
        content: "Co-owner added successfully",
      });
      await refreshCoOwnerData(resourceId);
      fetchConnectors();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to add co-owner"));
    }
  };

  const onRemoveCoOwner = async (resourceId, userId) => {
    try {
      await axiosPrivate.delete(
        getUrl(`connector/${resourceId}/owners/${userId}/`),
        {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }
      );
      setAlertDetails({
        type: "success",
        content: "Co-owner removed successfully",
      });
      await refreshCoOwnerData(resourceId);
      fetchConnectors();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to remove co-owner"));
    }
  };

  const handleConnectorSaved = () => {
    setModalVisible(false);
    setEditingConnector(null);
    fetchConnectors();
    setAlertDetails({
      type: "success",
      content: editingConnector
        ? "Connector updated successfully"
        : "Connector created successfully",
    });
  };

  const renderCreateConnectorButtons = useCallback(
    () => (
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={handleCreateConnector}
      >
        New Connector
      </Button>
    ),
    []
  );

  return (
    <div className="connectors-layout">
      <ToolNavBar
        title="Connectors"
        enableSearch
        setSearchList={setDisplayList}
        onSearch={onSearch}
        CustomButtons={renderCreateConnectorButtons}
      />
      <div className="connectors-pg-layout">
        <div className="connectors-pg-body">
          <ViewTools
            listOfTools={displayList}
            isLoading={loading}
            handleDelete={handleDeleteConnector}
            handleEdit={handleEditConnector}
            handleShare={handleShareConnector}
            handleCoOwner={handleCoOwner}
            setOpenAddTool={setModalVisible}
            idProp="id"
            titleProp="connector_name"
            descriptionProp="connector_type"
            iconProp="icon"
            showOwner={true}
            type="Connector"
            isEmpty={!displayList.length}
            centered
            isClickable={false}
          />
        </div>
      </div>
      <AddSourceModal
        open={modalVisible}
        setOpen={setModalVisible}
        isConnector={true}
        addNewItem={handleConnectorSaved}
        editItemId={editingConnector?.id}
        setEditItemId={setEditingConnector}
      />
      <SharePermission
        open={shareModalVisible}
        setOpen={setShareModalVisible}
        sharedItem={sharingConnector}
        allUsers={userList}
        onApply={handleShareSave}
        permissionEdit={isPermissionEdit}
        loading={isShareLoading}
        isSharableToOrg={true}
      />
      <CoOwnerManagement
        open={coOwnerOpen}
        setOpen={setCoOwnerOpen}
        resourceId={coOwnerResourceId}
        resourceType="Connector"
        allUsers={coOwnerAllUsers}
        coOwners={coOwnerData.coOwners}
        createdBy={coOwnerData.createdBy}
        loading={coOwnerLoading}
        onAddCoOwner={onAddCoOwner}
        onRemoveCoOwner={onRemoveCoOwner}
      />
    </div>
  );
}

export default ConnectorsPage;
