import { useState, useEffect, useCallback } from "react";
import { Button } from "antd";
import { PlusOutlined } from "@ant-design/icons";

import { useAxiosPrivate } from "../hooks/useAxiosPrivate";
import { useSessionStore } from "../store/session-store";
import { useAlertStore } from "../store/alert-store";
import { useExceptionHandler } from "../hooks/useExceptionHandler";
import useRequestUrl from "../hooks/useRequestUrl";
import "./ConnectorsPage.css";
import { ToolNavBar } from "../components/navigations/tool-nav-bar/ToolNavBar";
import { ViewTools } from "../components/custom-tools/view-tools/ViewTools";
import { SharePermission } from "../components/widgets/share-permission/SharePermission";
import { AddSourceModal } from "../components/input-output/add-source-modal/AddSourceModal";

function ConnectorsPage() {
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConnector, setEditingConnector] = useState(null);
  const [shareModalVisible, setShareModalVisible] = useState(false);
  const [sharingConnector, setSharingConnector] = useState(null);
  const [userList, setUserList] = useState([]);
  const [isPermissionEdit, setIsPermissionEdit] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();

  useEffect(() => {
    fetchConnectors();
    fetchUsers();
  }, []);

  const fetchConnectors = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(getUrl("connector/"));
      setConnectors(response.data || []);
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
        users.map((user) => ({
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

  const handleShareConnector = (_event, connector, isEdit) => {
    setSharingConnector(connector);
    setIsPermissionEdit(isEdit);
    setShareModalVisible(true);
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
        CustomButtons={renderCreateConnectorButtons}
      />
      <div className="connectors-pg-layout">
        <div className="connectors-pg-body">
          <ViewTools
            listOfTools={connectors}
            isLoading={loading}
            handleDelete={handleDeleteConnector}
            handleEdit={handleEditConnector}
            handleShare={handleShareConnector}
            setOpenAddTool={setModalVisible}
            idProp="id"
            titleProp="connector_name"
            descriptionProp="connector_type"
            iconProp="icon"
            showOwner={true}
            type="Connector"
            isEmpty={!connectors.length}
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
        adapter={sharingConnector}
        allUsers={userList}
        onApply={handleShareSave}
        permissionEdit={isPermissionEdit}
        loading={isShareLoading}
        isSharableToOrg={true}
      />
    </div>
  );
}

export default ConnectorsPage;
