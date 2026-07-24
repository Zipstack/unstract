import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { unwrapList } from "../../../helpers/pagination";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCoOwnerManagement } from "../../../hooks/useCoOwnerManagement";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { usePaginatedList } from "../../../hooks/usePaginatedList";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ViewTools } from "../../custom-tools/view-tools/ViewTools";
import { groupsService } from "../../groups/groups-service.js";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import "../../input-output/data-source-card/DataSourceCard.css";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { CoOwnerManagement } from "../../widgets/co-owner-management/CoOwnerManagement";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import "./ToolSettings.css";

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

const DEFAULT_PAGE_SIZE = 10;

function ToolSettings({ type }) {
  const [isLoading, setIsLoading] = useState(false);
  const [adapterList, setAdapterList] = useState([]);
  // Ref forwards the fetch fn to the pagination hook (avoids declaration ordering)
  const fetchListRef = useRef(null);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [adapterDetails, setAdapterDetails] = useState(null);
  const [userList, setUserList] = useState([]);
  const [groupList, setGroupList] = useState([]);
  const groupsApi = groupsService();
  const [openAddSourcesModal, setOpenAddSourcesModal] = useState(false);
  const [openSharePermissionModal, setOpenSharePermissionModal] =
    useState(false);
  const [isPermissonEdit, setIsPermissionEdit] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const adapterCoOwnerService = useMemo(
    () => ({
      getAllUsers: () =>
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
        }),
      getSharedUsers: (id) =>
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/users/${id}/`,
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
      addCoOwner: (id, userId) =>
        axiosPrivate({
          method: "POST",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${id}/owners/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: { user_id: userId },
        }),
      removeCoOwner: (id, userId) =>
        axiosPrivate({
          method: "DELETE",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${id}/owners/${userId}/`,
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
    }),
    [sessionDetails?.orgId, sessionDetails?.csrfToken],
  );

  const {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    handlePaginationChange,
    handleSearch,
  } = usePaginatedList({
    fetchData: (...args) => fetchListRef.current?.(...args),
    defaultPageSize: DEFAULT_PAGE_SIZE,
  });

  // Refresh the current page (preserves page + active search) after mutations
  const handleListRefresh = useCallback(
    () =>
      fetchListRef.current?.(
        pagination.current,
        pagination.pageSize,
        searchTerm,
      ),
    [pagination.current, pagination.pageSize, searchTerm],
  );

  const {
    coOwnerOpen,
    setCoOwnerOpen,
    coOwnerData,
    coOwnerLoading,
    coOwnerAllUsers,
    coOwnerResourceId,
    handleCoOwner: handleCoOwnerAction,
    onAddCoOwner,
    onRemoveCoOwner,
  } = useCoOwnerManagement({
    service: adapterCoOwnerService,
    setAlertDetails,
    onListRefresh: handleListRefresh,
  });
  const { posthogEventText, setPostHogCustomEvent } = usePostHogEvents();

  // Adapter type is a separate listing; reset paging and search when it changes.
  useEffect(() => {
    setSearchTerm("");
    setAdapterList([]);
    if (!type) {
      return;
    }
    getAdapters(1, DEFAULT_PAGE_SIZE, "");
  }, [type]);

  const getAdapters = (page = 1, pageSize = DEFAULT_PAGE_SIZE, search = "") => {
    const params = {
      adapter_type: type.toUpperCase(),
      page,
      page_size: pageSize,
    };
    if (search) {
      params.search = search;
    }
    setIsLoading(true);
    axiosPrivate({
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
      params,
    })
      .then((res) => {
        const results = unwrapList(res);
        const total = res?.data?.count ?? results.length;
        // Deleting the last row on a page leaves it empty; step back a page.
        if (results.length === 0 && page > 1 && total > 0) {
          getAdapters(page - 1, pageSize, search);
          return;
        }
        setAdapterList(results);
        setPagination((prev) => ({ ...prev, current: page, pageSize, total }));
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  // Effect, not a render-time write: mutating a ref during render is unsafe
  // under concurrent rendering, where a render can be discarded.
  useEffect(() => {
    fetchListRef.current = getAdapters;
  });

  const addNewItem = () => handleListRefresh();

  const handleDeleteSuccess = () => handleListRefresh();

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
      .then(() => handleDeleteSuccess())
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
    groupsApi
      .listGroups()
      .then((res) => {
        const items = Array.isArray(res?.data) ? res.data : [];
        setGroupList(items.map((g) => ({ id: g.id, name: g.name })));
      })
      .catch(() => setGroupList([]));
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
            is_admin: user?.is_admin,
          })),
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      })
      .finally(() => {
        setIsShareLoading(false);
      });
  };

  const onShare = (userIds, adapter, shareWithEveryone, groupIds = []) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter?.id}/share/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: {
        shared_users: userIds,
        shared_to_org: shareWithEveryone || false,
        shared_groups: groupIds,
      },
    };
    axiosPrivate(requestOptions)
      .then(() => {
        setOpenSharePermissionModal(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update sharing"));
      });
  };

  const handleCoOwner = (_event, adapter) => {
    if (!adapter?.id) return;
    if (adapter?.is_deprecated) {
      setAlertDetails({
        type: "error",
        content: "This adapter has been deprecated and cannot be managed.",
      });
      return;
    }
    handleCoOwnerAction(adapter.id);
  };

  const handleOpenAddSourceModal = () => {
    setOpenAddSourcesModal(true);

    try {
      setPostHogCustomEvent(posthogEventText[type], {
        info: `Clicked on '+ ${btnText[type]}' button`,
      });
    } catch (_err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  return (
    <div className="plt-tool-settings-layout">
      <ToolNavBar
        title={titles[type]}
        enableSearch
        searchKey={type}
        onSearch={(value) => handleSearch(value)}
        customButtons={
          <CustomButton
            type="primary"
            onClick={handleOpenAddSourceModal}
            icon={<PlusOutlined />}
          >
            {btnText[type]}
          </CustomButton>
        }
      />
      <IslandLayout>
        <div className="plt-tool-settings-layout-2">
          <div className="plt-tool-settings-body">
            <ViewTools
              listOfTools={adapterList}
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
              isEmpty={!adapterList.length && !searchTerm}
              centered
              isClickable={false}
              handleShare={handleShare}
              handleCoOwner={handleCoOwner}
              showOwner={true}
              showModified
              type="Adapter"
              pagination={{
                ...pagination,
                onChange: handlePaginationChange,
                itemLabel: "adapters",
              }}
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
        adapter={adapterDetails}
        permissionEdit={isPermissonEdit}
        loading={isShareLoading}
        allUsers={userList}
        allGroups={groupList}
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
