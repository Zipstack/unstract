import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { deploymentApiTypes, displayURL } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useExecutionLogs } from "../../../hooks/useExecutionLogs";
import { usePaginatedList } from "../../../hooks/usePaginatedList";
import usePipelineHelper from "../../../hooks/usePipelineHelper.js";
import {
  useInitialFetchCount,
  usePromptStudioModal,
} from "../../../hooks/usePromptStudioFetchCount";
import { useScrollRestoration } from "../../../hooks/useScrollRestoration";
import { useShareModal } from "../../../hooks/useShareModal";
import { useAlertStore } from "../../../store/alert-store";
import { usePromptStudioStore } from "../../../store/prompt-studio-store";
import { useSessionStore } from "../../../store/session-store";
import { usePromptStudioService } from "../../api/prompt-studio-service";
import { PromptStudioModal } from "../../common/PromptStudioModal";
import { LogsModal } from "../../pipelines-or-deployments/log-modal/LogsModal.jsx";
import { NotificationModal } from "../../pipelines-or-deployments/notification-modal/NotificationModal.jsx";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import { CreateApiDeploymentModal } from "../create-api-deployment-modal/CreateApiDeploymentModal";
import { DeleteModal } from "../delete-modal/DeleteModal";
import { DisplayCode } from "../display-code/DisplayCode";
import { Layout } from "../layout/Layout";
import { ManageKeys } from "../manage-keys/ManageKeys";
import { createApiDeploymentCardConfig } from "./ApiDeploymentCardConfig.jsx";
import { apiDeploymentsService } from "./api-deployments-service";

function ApiDeployment() {
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const location = useLocation();
  const apiDeploymentsApiService = apiDeploymentsService();
  const workflowApiService = workflowService();
  const [isTableLoading, setIsTableLoading] = useState(true);
  const [openAddApiModal, setOpenAddApiModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [openCodeModal, setOpenCodeModal] = useState(false);
  const [openManageKeysModal, setOpenManageKeysModal] = useState(false);
  const [selectedRow, setSelectedRow] = useState({});
  const [tableData, setTableData] = useState([]);
  const [filteredData, setFilteredData] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [isEdit, setIsEdit] = useState(false);
  const [workflowEndpointList, setWorkflowEndpointList] = useState([]);
  const handleException = useExceptionHandler();
  const axiosPrivate = useAxiosPrivate();
  const { getApiKeys, downloadPostmanCollection } = usePipelineHelper();
  const [openNotificationModal, setOpenNotificationModal] = useState(false);
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();

  // Ref to forward the fetch function to hooks (avoids declaration ordering)
  const fetchListRef = useRef(null);

  const {
    pagination,
    setPagination,
    searchTerm,
    setSearchTerm,
    handlePaginationChange,
    handleSearch,
  } = usePaginatedList({
    fetchData: (...args) => fetchListRef.current?.(...args),
  });

  const { scrollRestoreId, activateScrollRestore, clearPendingScroll } =
    useScrollRestoration({
      location,
      setSearchTerm,
      setPagination,
      fetchData: (...args) => fetchListRef.current?.(...args),
    });

  const {
    openLogsModal,
    setOpenLogsModal,
    executionLogs,
    executionLogsTotalCount,
    isFetchingLogs,
    handleFetchLogs,
    handleViewLogs,
  } = useExecutionLogs({
    axiosPrivate,
    handleException,
    sessionDetails,
    setAlertDetails,
  });

  const {
    openShareModal,
    setOpenShareModal,
    allUsers,
    isLoadingShare,
    handleShare,
    onShare,
  } = useShareModal({
    apiService: apiDeploymentsApiService,
    setSelectedItem: setSelectedRow,
    setAlertDetails,
    handleException,
    refreshList: () =>
      getApiDeploymentList(pagination.current, pagination.pageSize, searchTerm),
  });

  const initialFetchComplete = useInitialFetchCount(
    fetchCount,
    getPromptStudioCount,
  );

  useEffect(() => {
    getApiDeploymentList();
    getWorkflows();
  }, []);

  useEffect(() => {
    setFilteredData(tableData);
  }, [tableData]);

  const getWorkflows = () => {
    workflowApiService
      .getWorkflowEndpointList("SOURCE", "API")
      .then((res) => {
        setWorkflowEndpointList(res?.data);
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Unable to get workflow list.",
        });
      });
  };

  const getApiDeploymentList = (page = 1, pageSize = 10, search = "") => {
    setIsTableLoading(true);

    apiDeploymentsApiService
      .getApiDeploymentsList(page, pageSize, search)
      .then((res) => {
        const data = res?.data;
        const results = data.results || data;
        setTableData(results);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total:
            data.count !== null && data.count !== undefined
              ? data.count
              : data.results
                ? data.results.length
                : data.length,
        }));

        activateScrollRestore();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
        clearPendingScroll();
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  };

  fetchListRef.current = getApiDeploymentList;

  const deleteApiDeployment = () => {
    apiDeploymentsApiService
      .deleteApiDeployment(selectedRow.id)
      .then((res) => {
        setOpenDeleteModal(false);
        getApiDeploymentList(
          pagination.current,
          pagination.pageSize,
          searchTerm,
        );
        setAlertDetails({
          type: "success",
          content: "API Deployment Deleted Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const updateStatus = (record) => {
    const newStatus = !record?.is_active;
    // Optimistic update - no loading spinner
    setTableData((prev) =>
      prev.map((item) =>
        item.id === record.id ? { ...item, is_active: newStatus } : item,
      ),
    );

    apiDeploymentsApiService
      .updateApiDeployment({ ...record, is_active: newStatus })
      .catch((err) => {
        // Revert on error
        setTableData((prev) =>
          prev.map((item) =>
            item.id === record.id ? { ...item, is_active: !newStatus } : item,
          ),
        );
        setAlertDetails(handleException(err));
      });
  };

  const openAddModal = (edit) => {
    setIsEdit(edit);
    setOpenAddApiModal(true);
  };

  // Handlers for card view actions
  const handleEditDeployment = () => {
    openAddModal(true);
  };

  const handleDeleteDeployment = () => {
    setOpenDeleteModal(true);
  };

  const handleViewLogsDeployment = (deployment) => {
    handleViewLogs(deployment, setSelectedRow);
  };

  const handleManageKeysDeployment = (deployment) => {
    setSelectedRow(deployment);
    getApiKeys(
      apiDeploymentsApiService,
      deployment.id,
      setApiKeys,
      setOpenManageKeysModal,
    );
  };

  const handleSetupNotificationsDeployment = (deployment) => {
    setSelectedRow(deployment);
    setOpenNotificationModal(true);
  };

  const handleCodeSnippetsDeployment = (deployment) => {
    setSelectedRow(deployment);
    setOpenCodeModal(true);
  };

  const handleDownloadPostmanDeployment = (deployment) => {
    downloadPostmanCollection(apiDeploymentsApiService, deployment.id);
  };

  // Card view configuration
  const apiDeploymentCardConfig = useMemo(
    () =>
      createApiDeploymentCardConfig({
        setSelectedRow,
        updateStatus,
        sessionDetails,
        location,
        onEdit: handleEditDeployment,
        onShare: handleShare,
        onDelete: handleDeleteDeployment,
        onViewLogs: handleViewLogsDeployment,
        onManageKeys: handleManageKeysDeployment,
        onSetupNotifications: handleSetupNotificationsDeployment,
        onCodeSnippets: handleCodeSnippetsDeployment,
        onDownloadPostman: handleDownloadPostmanDeployment,
        listContext: {
          page: pagination.current,
          pageSize: pagination.pageSize,
          searchTerm,
        },
      }),
    [
      sessionDetails,
      location,
      pagination.current,
      pagination.pageSize,
      searchTerm,
    ],
  );

  // Using the custom hook to manage modal state
  const { showModal, handleModalClose } = usePromptStudioModal(
    initialFetchComplete,
    isLoading,
    count,
  );

  return (
    <>
      {showModal && (
        <PromptStudioModal onClose={handleModalClose} showModal={showModal} />
      )}
      <Layout
        type="api"
        tableData={filteredData}
        isTableLoading={isTableLoading}
        openAddModal={openAddModal}
        cardConfig={apiDeploymentCardConfig}
        listMode={true}
        scrollToId={scrollRestoreId}
        enableSearch={true}
        onSearch={handleSearch}
        setSearchList={setFilteredData}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          onChange: handlePaginationChange,
        }}
      />
      {openAddApiModal && (
        <CreateApiDeploymentModal
          open={openAddApiModal}
          setOpen={setOpenAddApiModal}
          setTableData={setTableData}
          isEdit={isEdit}
          selectedRow={selectedRow}
          openCodeModal={setOpenCodeModal}
          setSelectedRow={setSelectedRow}
          workflowEndpointList={workflowEndpointList}
        />
      )}
      <DeleteModal
        open={openDeleteModal}
        setOpen={setOpenDeleteModal}
        deleteRecord={deleteApiDeployment}
      />
      <ManageKeys
        isDialogOpen={openManageKeysModal}
        setDialogOpen={setOpenManageKeysModal}
        apiKeys={apiKeys}
        setApiKeys={setApiKeys}
        selectedApiRow={selectedRow}
        apiService={apiDeploymentsApiService}
        type={deploymentApiTypes.api}
      />
      <DisplayCode
        isDialogOpen={openCodeModal}
        setDialogOpen={setOpenCodeModal}
        url={displayURL(selectedRow?.api_endpoint)}
      />
      <LogsModal
        open={openLogsModal}
        setOpen={setOpenLogsModal}
        logRecord={executionLogs}
        totalLogs={executionLogsTotalCount}
        fetchExecutionLogs={handleFetchLogs}
        loading={isFetchingLogs}
      />
      <NotificationModal
        open={openNotificationModal}
        setOpen={setOpenNotificationModal}
        type={deploymentApiTypes.api}
        id={selectedRow?.id}
      />
      <SharePermission
        open={openShareModal}
        setOpen={setOpenShareModal}
        adapter={selectedRow}
        permissionEdit={true}
        loading={isLoadingShare}
        allUsers={allUsers}
        onApply={onShare}
        isSharableToOrg={true}
      />
    </>
  );
}

export { ApiDeployment };
