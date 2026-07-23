import { ArrowDownOutlined, PlusOutlined } from "@ant-design/icons";
import { Space } from "antd";
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
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { groupsService } from "../../groups/groups-service.js";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { CoOwnerManagement } from "../../widgets/co-owner-management/CoOwnerManagement";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { ResourceTable } from "../../widgets/resource-table/ResourceTable";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { AddCustomToolFormModal } from "../add-custom-tool-form-modal/AddCustomToolFormModal";
import { ImportTool } from "../import-tool/ImportTool";
import "./ListOfTools.css";

const DEFAULT_PAGE_SIZE = 10;

const DefaultCustomButtons = ({
  setOpenImportTool,
  isImportLoading,
  handleNewProjectBtnClick,
}) => {
  return (
    <Space gap={16}>
      <CustomButton
        type="default"
        icon={<ArrowDownOutlined />}
        onClick={() => setOpenImportTool(true)}
        loading={isImportLoading}
      >
        Import Project
      </CustomButton>
      <CustomButton
        type="primary"
        icon={<PlusOutlined />}
        onClick={handleNewProjectBtnClick}
      >
        New Project
      </CustomButton>
    </Space>
  );
};

DefaultCustomButtons.propTypes = {
  setOpenImportTool: PropTypes.func.isRequired,
  isImportLoading: PropTypes.bool.isRequired,
  handleNewProjectBtnClick: PropTypes.func.isRequired,
};

function ListOfTools({ segmentOptions, segmentValue, onSegmentChange }) {
  const [isLoading, setIsLoading] = useState(false);
  const [openAddTool, setOpenAddTool] = useState(false);
  const [openImportTool, setOpenImportTool] = useState(false);
  const [isImportLoading, setIsImportLoading] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const groupsApi = groupsService();

  // undefined = not fetched yet (spinner); [] = fetched-empty (empty state)
  const [displayList, setDisplayList] = useState();
  const [isEdit, setIsEdit] = useState(false);
  const [promptDetails, setPromptDetails] = useState(null);
  const [openSharePermissionModal, setOpenSharePermissionModal] =
    useState(false);
  const [isPermissionEdit, setIsPermissionEdit] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [allUserList, setAllUserList] = useState([]);
  const [allGroupList, setAllGroupList] = useState([]);
  // Ref forwards the fetch fn to the pagination hook (avoids declaration order).
  const fetchListRef = useRef(null);
  // Monotonic request token so a stale response can't overwrite a newer one.
  const seqRef = useRef(0);

  const promptStudioCoOwnerService = useMemo(
    () => ({
      getAllUsers: () =>
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
        }),
      getSharedUsers: (id) =>
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/users/${id}`,
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
      addCoOwner: (id, userId) =>
        axiosPrivate({
          method: "POST",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${id}/owners/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: { user_id: userId },
        }),
      removeCoOwner: (id, userId) =>
        axiosPrivate({
          method: "DELETE",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${id}/owners/${userId}/`,
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
    }),
    [axiosPrivate, sessionDetails?.orgId, sessionDetails?.csrfToken],
  );

  const {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    sort,
    handlePaginationChange,
    handleSearch,
    handleSortChange,
  } = usePaginatedList({
    fetchData: (...args) => fetchListRef.current?.(...args),
    defaultPageSize: DEFAULT_PAGE_SIZE,
  });

  // Refresh the current page (preserves page + active search/sort) after mutations
  const handleListRefresh = useCallback(
    () =>
      fetchListRef.current?.(
        pagination.current,
        pagination.pageSize,
        searchTerm,
        sort.sortBy,
        sort.order,
      ),
    [
      pagination.current,
      pagination.pageSize,
      searchTerm,
      sort.sortBy,
      sort.order,
    ],
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
    service: promptStudioCoOwnerService,
    setAlertDetails,
    onListRefresh: handleListRefresh,
  });

  const getListOfTools = useCallback(
    (
      page = 1,
      pageSize = DEFAULT_PAGE_SIZE,
      search = "",
      sortBy = "",
      order = "asc",
    ) => {
      const params = buildPagedParams({
        page,
        pageSize,
        search,
        sortBy,
        order,
      });
      const seq = ++seqRef.current;
      setIsLoading(true);
      return axiosPrivate({
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`,
        headers: { "X-CSRFToken": sessionDetails?.csrfToken },
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
              getListOfTools(page - 1, pageSize, search, sortBy, order),
          }),
        )
        .catch((err) => {
          setAlertDetails(
            handleException(err, "Failed to get the list of tools"),
          );
          // Avoid an indefinite spinner when the first fetch fails.
          setDisplayList((prev) => prev ?? []);
        })
        .finally(() => {
          setIsLoading(false);
        });
    },
    [
      sessionDetails?.orgId,
      sessionDetails?.csrfToken,
      axiosPrivate,
      setPagination,
      setAlertDetails,
      handleException,
    ],
  );
  fetchListRef.current = getListOfTools;

  useEffect(() => {
    setSearchTerm("");
    setDisplayList(undefined);
    getListOfTools(1, DEFAULT_PAGE_SIZE, "", "", "asc");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAddNewTool = (body) => {
    let method = "POST";
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`;
    const isEditFlow = editItem && Object.keys(editItem)?.length > 0;
    if (isEditFlow) {
      method = "PATCH";
      url += `${editItem?.tool_id}/`;
    }
    return new Promise((resolve, reject) => {
      const requestOptions = {
        method,
        url,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: body,
      };

      axiosPrivate(requestOptions)
        .then((res) => {
          setEditItem(null);
          // Refetch the current page to reflect server truth rather than
          // splicing a stale list (list-only fields like prompt_count).
          handleListRefresh();
          setOpenAddTool(false);
          resolve(res?.data);
        })
        .catch((err) => {
          reject(err);
        });
    });
  };

  const handleEdit = (_event, tool) => {
    if (!tool) {
      return;
    }
    setIsEdit(true);
    setEditItem(tool);
    setOpenAddTool(true);
  };

  const handleDelete = (_event, tool) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${tool.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => handleListRefresh())
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to Delete"));
      });
  };

  const showAddTool = () => {
    setEditItem(null);
    setIsEdit(false);
    setOpenAddTool(true);
  };

  const handleNewProjectBtnClick = () => {
    showAddTool();

    try {
      setPostHogCustomEvent("intent_new_ps_project", {
        info: "Clicked on '+ New Project' button",
      });
    } catch (_err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const handleImportProject = (file, selectedAdapters) => {
    try {
      setPostHogCustomEvent("intent_tool_import_project", {
        info: "Importing project from projects list",
        file_name: file.name,
      });
    } catch (_err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    setIsImportLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    // Add selected adapter IDs to the form data
    if (selectedAdapters) {
      formData.append("llm_adapter_id", selectedAdapters.llm);
      formData.append("vector_db_adapter_id", selectedAdapters.vectorDb);
      formData.append("embedding_adapter_id", selectedAdapters.embedding);
      formData.append("x2text_adapter_id", selectedAdapters.x2text);
    }

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/project-transfer/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: formData,
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        const {
          message,
          warning,
          needs_adapter_config: needsAdapterConfig,
        } = response.data;

        setAlertDetails({
          type: needsAdapterConfig ? "warning" : "success",
          content: warning ? `${message} ${warning}` : message,
        });
        setOpenImportTool(false);

        // Refresh the list of tools to show the new imported project
        handleListRefresh();
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to import project"));
      })
      .finally(() => {
        setIsImportLoading(false);
      });
  };

  const handleShare = (_event, promptProject, isEditShare) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/users/${promptProject?.tool_id}`,
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
        setAllGroupList(items.map((g) => ({ id: g.id, name: g.name })));
      })
      .catch(() => setAllGroupList([]));
    axiosPrivate(requestOptions)
      .then((res) => {
        setOpenSharePermissionModal(true);
        setPromptDetails(res?.data);
        setIsPermissionEdit(isEditShare);
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
        setAllUserList(
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
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${adapter?.tool_id}/share/`,
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
        // Close only on success; keep the modal open on failure so the user
        // can see the rejected entries and retry.
        setOpenSharePermissionModal(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      });
  };

  const handleCoOwner = (_event, tool) => {
    handleCoOwnerAction(tool.tool_id);
  };

  const customButtonsElement = useMemo(
    () => (
      <DefaultCustomButtons
        setOpenImportTool={setOpenImportTool}
        isImportLoading={isImportLoading}
        handleNewProjectBtnClick={handleNewProjectBtnClick}
      />
    ),
    [isImportLoading],
  );

  return (
    <>
      <ToolNavBar
        title="Prompt Studio"
        enableSearch
        onSearch={(value) => handleSearch(value)}
        customButtons={customButtonsElement}
        segmentOptions={segmentOptions}
        segmentValue={segmentValue}
        segmentFilter={onSegmentChange}
      />
      <div className="list-of-tools-layout">
        <div className="list-of-tools-island">
          <div className="list-of-tools-body">
            {displayList === undefined && <SpinnerLoader />}
            {displayList?.length === 0 && !searchTerm && (
              <EmptyState
                text="No prompt projects available"
                btnText="New Project"
                handleClick={handleNewProjectBtnClick}
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
                titleProp="tool_name"
                descriptionProp="description"
                iconProp="icon"
                idProp="tool_id"
                dateProp="created_at"
                ownerEmailProp="created_by_email"
                handleEdit={handleEdit}
                handleShare={handleShare}
                handleDelete={handleDelete}
                handleCoOwner={handleCoOwner}
                sessionDetails={sessionDetails}
                isClickable={true}
                type="Prompt Project"
              />
            )}
          </div>
        </div>
      </div>
      {openAddTool && (
        <AddCustomToolFormModal
          open={openAddTool}
          setOpen={setOpenAddTool}
          editItem={editItem}
          isEdit={isEdit}
          handleAddNewTool={handleAddNewTool}
        />
      )}
      <ImportTool
        open={openImportTool}
        setOpen={setOpenImportTool}
        onImport={handleImportProject}
        loading={isImportLoading}
      />
      <SharePermission
        open={openSharePermissionModal}
        setOpen={setOpenSharePermissionModal}
        adapter={promptDetails}
        permissionEdit={isPermissionEdit}
        loading={isShareLoading}
        allUsers={allUserList}
        allGroups={allGroupList}
        onApply={onShare}
        isSharableToOrg={true}
      />
      <CoOwnerManagement
        open={coOwnerOpen}
        setOpen={setCoOwnerOpen}
        resourceId={coOwnerResourceId}
        resourceType="Prompt Project"
        allUsers={coOwnerAllUsers}
        coOwners={coOwnerData.coOwners}
        createdBy={coOwnerData.createdBy}
        loading={coOwnerLoading}
        onAddCoOwner={onAddCoOwner}
        onRemoveCoOwner={onRemoveCoOwner}
      />
    </>
  );
}

ListOfTools.propTypes = {
  segmentOptions: PropTypes.arrayOf(PropTypes.string),
  segmentValue: PropTypes.string,
  onSegmentChange: PropTypes.func,
};

export { ListOfTools };
