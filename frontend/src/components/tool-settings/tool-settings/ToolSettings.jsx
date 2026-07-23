import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCoOwnerManagement } from "../../../hooks/useCoOwnerManagement";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import {
  applyPagedResponse,
  buildPagedParams,
  usePaginatedList,
} from "../../../hooks/usePaginatedList";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { groupsService } from "../../groups/groups-service.js";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import "../../input-output/data-source-card/DataSourceCard.css";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { CoOwnerModal } from "../../widgets/co-owner-management/CoOwnerModal";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { ResourceTable } from "../../widgets/resource-table/ResourceTable";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
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
  // undefined = not fetched yet (spinner); [] = fetched-empty (empty state)
  const [displayList, setDisplayList] = useState();
  // Fetch failure (vs. genuinely empty) — drives a retryable error state.
  const [loadError, setLoadError] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  // Monotonic request token so a stale response can't overwrite a newer one.
  const seqRef = useRef(0);

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
    sort,
    fetchRef,
    handlePaginationChange,
    handleSearch,
    handleSortChange,
    handleListRefresh,
  } = usePaginatedList({ defaultPageSize: DEFAULT_PAGE_SIZE });

  const coOwner = useCoOwnerManagement({
    service: adapterCoOwnerService,
    setAlertDetails,
    onListRefresh: handleListRefresh,
  });
  const { posthogEventText, setPostHogCustomEvent } = usePostHogEvents();

  const getAdapters = useCallback(
    (
      page = 1,
      pageSize = DEFAULT_PAGE_SIZE,
      search = "",
      sortBy = "",
      order = "asc",
    ) => {
      if (!type) {
        return;
      }
      const params = buildPagedParams({
        page,
        pageSize,
        search,
        sortBy,
        order,
      });
      params.adapter_type = type.toUpperCase();
      const seq = ++seqRef.current;
      setLoadError(false);
      setIsLoading(true);
      return axiosPrivate({
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter`,
        params,
      })
        .then((res) =>
          applyPagedResponse({
            data: res?.data,
            page,
            pageSize,
            seq,
            latestSeqRef: seqRef,
            setList: setDisplayList,
            setPagination,
            refetchPrevPage: () =>
              getAdapters(page - 1, pageSize, search, sortBy, order),
          }),
        )
        .catch((err) => {
          // A newer request superseded this one — don't surface its error.
          if (seq !== seqRef.current) {
            return;
          }
          setAlertDetails(handleException(err));
          // Surface a retryable error instead of a misleading empty state.
          setLoadError(true);
        })
        .finally(() => {
          // Only the newest request owns the shared loading state.
          if (seq === seqRef.current) {
            setIsLoading(false);
          }
        });
    },
    [
      type,
      sessionDetails?.orgId,
      axiosPrivate,
      setPagination,
      setAlertDetails,
      handleException,
    ],
  );
  fetchRef.current = getAdapters;

  useEffect(() => {
    setSearchTerm("");
    setDisplayList(undefined);
    if (!type) {
      return;
    }
    getAdapters(1, DEFAULT_PAGE_SIZE, "", "", "asc");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);

  // New/edited adapters land on some page under the active sort — refetch the
  // current page to reflect server truth rather than splicing a stale array.
  const addNewItem = () => handleListRefresh();

  const handleDelete = (_event, adapter) => {
    setIsLoading(true);
    axiosPrivate({
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter?.id}/`,
      headers: { "X-CSRFToken": sessionDetails?.csrfToken },
    })
      .then(() => handleListRefresh())
      .catch((err) => {
        setAlertDetails(handleException(err));
        // Refresh only runs on success; clear loading here so a failed delete
        // doesn't leave the table stuck under its spinner.
        setIsLoading(false);
      });
  };

  const handleEdit = (_event, item) => {
    if (item?.is_deprecated) {
      setAlertDetails({
        type: "error",
        content:
          "This adapter has been deprecated and cannot be edited. Please remove it or use an alternative adapter.",
      });
      return;
    }
    setEditItemId(item?.id);
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
    if (!adapter?.id) {
      return;
    }
    if (adapter?.is_deprecated) {
      setAlertDetails({
        type: "error",
        content: "This adapter has been deprecated and cannot be managed.",
      });
      return;
    }
    coOwner.handleCoOwner(adapter.id);
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
            {displayList === undefined && !loadError && <SpinnerLoader />}
            {displayList === undefined && loadError && (
              <EmptyState
                text="Couldn't load. Please try again."
                btnText="Retry"
                handleClick={handleListRefresh}
              />
            )}
            {displayList?.length === 0 && !searchTerm && (
              <EmptyState
                text={`No ${titles[type]?.toLowerCase() || "adapters"} available`}
                btnText={btnText[type]}
                handleClick={handleOpenAddSourceModal}
              />
            )}
            {displayList?.length === 0 && searchTerm && (
              <EmptyState text="No results found for this search" />
            )}
            {displayList?.length > 0 && (
              <ResourceTable
                dataSource={displayList}
                loading={isLoading}
                pagination={pagination}
                sort={sort}
                onPaginationChange={handlePaginationChange}
                onSortChange={handleSortChange}
                titleProp="adapter_name"
                descriptionProp="description"
                iconProp="icon"
                idProp="id"
                dateProp="created_at"
                ownerEmailProp="created_by_email"
                handleEdit={handleEdit}
                handleShare={handleShare}
                handleDelete={handleDelete}
                handleCoOwner={handleCoOwner}
                sessionDetails={sessionDetails}
                isClickable={false}
                type="Adapter"
              />
            )}
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
      <CoOwnerModal coOwner={coOwner} resourceType="Adapter" />
    </div>
  );
}

ToolSettings.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolSettings };
