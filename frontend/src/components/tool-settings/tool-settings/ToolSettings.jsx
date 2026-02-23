import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import "../../input-output/data-source-card/DataSourceCard.css";
import "./ToolSettings.css";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { ViewTools } from "../../custom-tools/view-tools/ViewTools";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { CoOwnerManagement } from "../../widgets/co-owner-management/CoOwnerManagement";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useListSearch } from "../../../hooks/useListSearch";

const titles = {
  llm: "LLMs",
  vector_db: "Vector DBs",
  embedding: "Embeddings",
  x2text: "Text Extractor",
  ocr: "OCR",
};

const btnText = {
  llm: "New LLM Profile",
  vector_db: "New Vector DB Profile",
  embedding: "New Embedding Profile",
  x2text: "New Text Extractor",
  ocr: "New OCR",
};

function ToolSettings({ type }) {
  const [isLoading, setIsLoading] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [adapterDetails, setAdapterDetails] = useState(null);
  const [userList, setUserList] = useState([]);
  const [openAddSourcesModal, setOpenAddSourcesModal] = useState(false);
  const [openSharePermissionModal, setOpenSharePermissionModal] =
    useState(false);
  const [isPermissonEdit, setIsPermissionEdit] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const [coOwnerOpen, setCoOwnerOpen] = useState(false);
  const [coOwnerData, setCoOwnerData] = useState({
    coOwners: [],
    createdBy: null,
  });
  const [coOwnerLoading, setCoOwnerLoading] = useState(false);
  const [coOwnerAllUsers, setCoOwnerAllUsers] = useState([]);
  const [coOwnerResourceId, setCoOwnerResourceId] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { posthogEventText, setPostHogCustomEvent } = usePostHogEvents();
  const {
    displayList,
    setDisplayList,
    setMasterList,
    updateMasterList,
    onSearch,
    clearSearch,
  } = useListSearch("adapter_name");

  useEffect(() => {
    clearSearch();
    setMasterList([]);
    if (!type) {
      return;
    }
    getAdapters();
  }, [type]);

  const getAdapters = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/adapter?adapter_type=${type.toUpperCase()}`,
    };
    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        setMasterList(res?.data || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const addNewItem = (row, isEdit) => {
    if (isEdit) {
      updateMasterList((currentList) =>
        currentList.map((tableRow) => {
          if (tableRow?.id !== row?.id) {
            return tableRow;
          }
          return { ...tableRow, adapter_name: row?.adapter_name };
        })
      );
    } else {
      updateMasterList((currentList) => [...currentList, row]);
    }
  };

  const handleDeleteSuccess = (adapterId) => {
    updateMasterList((currentList) =>
      currentList.filter((row) => row?.id !== adapterId)
    );
  };

  const handleDelete = (_event, adapter) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then(() => handleDeleteSuccess(adapter?.id))
      .catch((err) => setAlertDetails(handleException(err)))
      .finally(() => setIsLoading(false));
  };

  const handleShare = (_event, adapter, isEdit) => {
    // Check if adapter is deprecated
    if (adapter?.is_deprecated) {
      setAlertDetails({
        type: "error",
        content:
          "This adapter has been deprecated and cannot be shared. Please remove it or use an alternative adapter.",
      });
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/users/${adapter.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    setIsShareLoading(true);
    getAllUsers();
    axiosPrivate(requestOptions)
      .then((res) => {
        setOpenSharePermissionModal(true);
        setAdapterDetails(res?.data);
        setIsPermissionEdit(isEdit);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsShareLoading(false);
      });
  };

  const getAllUsers = () => {
    setIsShareLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        const users = response?.data?.members || [];
        setUserList(
          users.map((user) => ({
            id: user?.id,
            email: user?.email,
          }))
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      })
      .finally(() => {
        setIsShareLoading(false);
      });
  };

  const onShare = (userIds, adapter, shareWithEveryone) => {
    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: {
        shared_users: userIds,
        shared_to_org: shareWithEveryone || false,
      },
    };
    axiosPrivate(requestOptions)
      .then((response) => {
        setOpenSharePermissionModal(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update sharing"));
      });
  };

  const handleCoOwner = async (_event, adapter) => {
    if (adapter?.is_deprecated) {
      setAlertDetails({
        type: "error",
        content: "This adapter has been deprecated and cannot be managed.",
      });
      return;
    }

    setCoOwnerResourceId(adapter.id);
    setCoOwnerLoading(true);
    setCoOwnerOpen(true);

    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
        }),
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/users/${adapter.id}/`,
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
      const res = await axiosPrivate({
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/users/${resourceId}/`,
        headers: { "X-CSRFToken": sessionDetails?.csrfToken },
      });
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
      await axiosPrivate({
        method: "POST",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${resourceId}/owners/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: { user_id: userId },
      });
      setAlertDetails({
        type: "success",
        content: "Co-owner added successfully",
      });
      await refreshCoOwnerData(resourceId);
      getAdapters();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to add co-owner"));
    }
  };

  const onRemoveCoOwner = async (resourceId, userId) => {
    try {
      await axiosPrivate({
        method: "DELETE",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${resourceId}/owners/${userId}/`,
        headers: { "X-CSRFToken": sessionDetails?.csrfToken },
      });
      setAlertDetails({
        type: "success",
        content: "Co-owner removed successfully",
      });
      await refreshCoOwnerData(resourceId);
      getAdapters();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to remove co-owner"));
    }
  };

  const handleOpenAddSourceModal = () => {
    setOpenAddSourcesModal(true);

    try {
      setPostHogCustomEvent(posthogEventText[type], {
        info: `Clicked on '+ ${btnText[type]}' button`,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  return (
    <div className="plt-tool-settings-layout">
      <ToolNavBar
        title={titles[type]}
        enableSearch
        searchKey={type}
        setSearchList={setDisplayList}
        onSearch={onSearch}
        CustomButtons={() => {
          return (
            <CustomButton
              type="primary"
              onClick={handleOpenAddSourceModal}
              icon={<PlusOutlined />}
            >
              {btnText[type]}
            </CustomButton>
          );
        }}
      />
      <IslandLayout>
        <div className="plt-tool-settings-layout-2">
          <div className="plt-tool-settings-body">
            <ViewTools
              listOfTools={displayList}
              isLoading={isLoading}
              handleDelete={handleDelete}
              setOpenAddTool={setOpenAddSourcesModal}
              handleEdit={(_event, item) => {
                // Check if adapter is deprecated
                if (item?.is_deprecated) {
                  setAlertDetails({
                    type: "error",
                    content:
                      "This adapter has been deprecated and cannot be edited. Please remove it or use an alternative adapter.",
                  });
                  return;
                }
                setEditItemId(item?.id);
              }}
              idProp="id"
              titleProp="adapter_name"
              descriptionProp="description"
              iconProp="icon"
              isEmpty={!displayList?.length}
              centered
              isClickable={false}
              handleShare={handleShare}
              handleCoOwner={handleCoOwner}
              showOwner={true}
              type="Adapter"
            />
          </div>
        </div>
      </IslandLayout>
      <AddSourceModal
        open={openAddSourcesModal}
        setOpen={setOpenAddSourcesModal}
        type={type}
        addNewItem={addNewItem}
        editItemId={editItemId}
        setEditItemId={setEditItemId}
      />
      <SharePermission
        open={openSharePermissionModal}
        setOpen={setOpenSharePermissionModal}
        sharedItem={adapterDetails}
        permissionEdit={isPermissonEdit}
        loading={isShareLoading}
        allUsers={userList}
        onApply={onShare}
        isSharableToOrg={true}
      />
      <CoOwnerManagement
        open={coOwnerOpen}
        setOpen={setCoOwnerOpen}
        resourceId={coOwnerResourceId}
        resourceType="Adapter"
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

ToolSettings.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolSettings };
