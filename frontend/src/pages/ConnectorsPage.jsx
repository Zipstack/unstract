import { PlusOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { groupsService } from "../components/groups/groups-service.js";
import { AddSourceModal } from "../components/input-output/add-source-modal/AddSourceModal";
import { ToolNavBar } from "../components/navigations/tool-nav-bar/ToolNavBar";
import { CoOwnerManagement } from "../components/widgets/co-owner-management/CoOwnerManagement";
import { EmptyState } from "../components/widgets/empty-state/EmptyState.jsx";
import { ResourceTable } from "../components/widgets/resource-table/ResourceTable";
import { SharePermission } from "../components/widgets/share-permission/SharePermission";
import { SpinnerLoader } from "../components/widgets/spinner-loader/SpinnerLoader.jsx";
import { useAxiosPrivate } from "../hooks/useAxiosPrivate";
import { useCoOwnerManagement } from "../hooks/useCoOwnerManagement";
import { useExceptionHandler } from "../hooks/useExceptionHandler";
import { usePaginatedList } from "../hooks/usePaginatedList";
import useRequestUrl from "../hooks/useRequestUrl";
import { useAlertStore } from "../store/alert-store";
import { useSessionStore } from "../store/session-store";
import "./ConnectorsPage.css";

const DEFAULT_PAGE_SIZE = 10;

function ConnectorsPage() {
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConnector, setEditingConnector] = useState(null);
  const [shareModalVisible, setShareModalVisible] = useState(false);
  const [sharingConnector, setSharingConnector] = useState(null);
  const [userList, setUserList] = useState([]);
  const [groupList, setGroupList] = useState([]);
  const [isPermissionEdit, setIsPermissionEdit] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);
  // undefined = not fetched yet (spinner); [] = fetched-empty (empty state)
  const [displayList, setDisplayList] = useState();
  const groupsApi = groupsService();

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();
  // Ref forwards the fetch fn to the pagination hook (avoids declaration order).
  const fetchListRef = useRef(null);

  const connectorCoOwnerService = useMemo(
    () => ({
      getAllUsers: () => axiosPrivate.get(getUrl("users/")),
      getSharedUsers: (id) =>
        axiosPrivate.get(getUrl(`connector/users/${id}/`), {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
      addCoOwner: (id, userId) =>
        axiosPrivate.post(
          getUrl(`connector/${id}/owners/`),
          { user_id: userId },
          {
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
              "Content-Type": "application/json",
            },
          },
        ),
      removeCoOwner: (id, userId) =>
        axiosPrivate.delete(getUrl(`connector/${id}/owners/${userId}/`), {
          headers: { "X-CSRFToken": sessionDetails?.csrfToken },
        }),
    }),
    [sessionDetails?.csrfToken],
  );

  const {
    pagination,
    setPagination,
    searchTerm,
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
    service: connectorCoOwnerService,
    setAlertDetails,
    onListRefresh: handleListRefresh,
  });

  const getConnectors = useCallback(
    (
      page = 1,
      pageSize = DEFAULT_PAGE_SIZE,
      search = "",
      sortBy = "",
      order = "asc",
    ) => {
      const params = { page, page_size: pageSize };
      if (search) {
        params.search = search;
      }
      if (sortBy) {
        params.sort_by = sortBy;
        params.order = order;
      }
      setLoading(true);
      axiosPrivate
        .get(getUrl("connector/"), { params })
        .then((res) => {
          const data = res?.data;
          // Endpoint is opt-in paginated: envelope when we send ?page, else a
          // bare array. Handle both so shared (dropdown) callers stay unaffected.
          const results = data?.results ?? data ?? [];
          const total = data?.count ?? results.length;
          // Deleting the last row on a page leaves it empty; step back a page.
          if (results.length === 0 && page > 1 && total > 0) {
            getConnectors(page - 1, pageSize, search, sortBy, order);
            return;
          }
          setDisplayList(results);
          setPagination((prev) => ({
            ...prev,
            current: page,
            pageSize,
            total,
          }));
        })
        .catch((err) => {
          setAlertDetails(handleException(err, "Failed to load connectors"));
          // Avoid an indefinite spinner when the first fetch fails.
          setDisplayList((prev) => prev ?? []);
        })
        .finally(() => {
          setLoading(false);
        });
    },
    [axiosPrivate, getUrl, setPagination, setAlertDetails, handleException],
  );
  fetchListRef.current = getConnectors;

  useEffect(() => {
    getConnectors(1, DEFAULT_PAGE_SIZE, "", "", "asc");
    fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          })),
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
      handleListRefresh();
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to delete connector"));
    }
  };

  const handleShareConnector = (_event, connector, isEdit) => {
    setSharingConnector(connector);
    setIsPermissionEdit(isEdit);
    setShareModalVisible(true);
    groupsApi
      .listGroups()
      .then((res) => {
        const items = Array.isArray(res?.data) ? res.data : [];
        setGroupList(items.map((g) => ({ id: g.id, name: g.name })));
      })
      .catch(() => setGroupList([]));
    // Seed the modal from the detail endpoint — the list row no longer
    // carries `shared_users`, and SharePermission gates all seeding on it;
    // seeding from the row would render "not shared" and Apply would then
    // silently wipe every existing share (same pattern as the other pages).
    setIsShareLoading(true);
    connectorCoOwnerService
      .getSharedUsers(connector.id)
      .then((res) => setSharingConnector(res?.data))
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Unable to fetch sharing information"),
        );
        setShareModalVisible(false);
      })
      .finally(() => setIsShareLoading(false));
  };

  const handleShareSave = async (
    userIds,
    connector,
    shareWithEveryone,
    groupIds = [],
  ) => {
    setIsShareLoading(true);
    try {
      const updateData = {
        shared_users: userIds,
        shared_to_org: shareWithEveryone || false,
        shared_groups: groupIds,
      };

      await axiosPrivate.post(
        getUrl(`connector/${connector.id}/share/`),
        updateData,
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        },
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

  const handleCoOwner = (_event, connector) => {
    if (!connector?.id) {
      return;
    }
    handleCoOwnerAction(connector.id);
  };

  const handleConnectorSaved = () => {
    setModalVisible(false);
    setEditingConnector(null);
    // New/edited connectors land on some page under the active sort — refetch
    // the current page to reflect server truth rather than splicing a stale array.
    handleListRefresh();
    setAlertDetails({
      type: "success",
      content: editingConnector
        ? "Connector updated successfully"
        : "Connector created successfully",
    });
  };

  const newConnectorButton = (
    <Button
      type="primary"
      icon={<PlusOutlined />}
      onClick={handleCreateConnector}
    >
      New Connector
    </Button>
  );

  return (
    <div className="connectors-layout">
      <ToolNavBar
        title="Connectors"
        enableSearch
        onSearch={(value) => handleSearch(value)}
        customButtons={newConnectorButton}
      />
      <div className="connectors-pg-layout">
        <div className="connectors-pg-body">
          {displayList === undefined && <SpinnerLoader />}
          {displayList?.length === 0 && !searchTerm && (
            <EmptyState
              text="No connectors available"
              btnText="New Connector"
              handleClick={handleCreateConnector}
            />
          )}
          {displayList?.length === 0 && searchTerm && (
            <EmptyState text="No results found for this search" />
          )}
          {displayList?.length > 0 && (
            <ResourceTable
              dataSource={displayList}
              loading={loading}
              pagination={pagination}
              sort={sort}
              onPaginationChange={handlePaginationChange}
              onSortChange={handleSortChange}
              titleProp="connector_name"
              descriptionProp="description"
              iconProp="icon"
              idProp="id"
              dateProp="created_at"
              ownerEmailProp="created_by_email"
              handleEdit={handleEditConnector}
              handleShare={handleShareConnector}
              handleDelete={handleDeleteConnector}
              handleCoOwner={handleCoOwner}
              sessionDetails={sessionDetails}
              isClickable={false}
              type="Connector"
            />
          )}
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
        allGroups={groupList}
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
