import PropTypes from "prop-types";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  deploymentApiTypes,
  deploymentsStaticContent,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useSessionStore } from "../../../store/session-store.js";
import { Layout } from "../../deployments/layout/Layout.jsx";
import { DeleteModal } from "../delete-modal/DeleteModal.jsx";
import { LogsModal } from "../log-modal/LogsModal.jsx";
import { EtlTaskDeploy } from "../etl-task-deploy/EtlTaskDeploy.jsx";
import FileHistoryModal from "../file-history-modal/FileHistoryModal.jsx";
import "./Pipelines.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { pipelineService } from "../pipeline-service.js";
import { ManageKeys } from "../../deployments/manage-keys/ManageKeys.jsx";
import usePipelineHelper from "../../../hooks/usePipelineHelper.js";
import useClearFileHistory from "../../../hooks/useClearFileHistory";
import { NotificationModal } from "../notification-modal/NotificationModal.jsx";
import { usePromptStudioStore } from "../../../store/prompt-studio-store";
import { PromptStudioModal } from "../../common/PromptStudioModal";
import { usePromptStudioService } from "../../api/prompt-studio-service";
import {
  useInitialFetchCount,
  usePromptStudioModal,
} from "../../../hooks/usePromptStudioFetchCount";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { createPipelineCardConfig } from "./PipelineCardConfig.jsx";
import { useExecutionLogs } from "../../../hooks/useExecutionLogs";
import { usePaginatedList } from "../../../hooks/usePaginatedList";
import { useScrollRestoration } from "../../../hooks/useScrollRestoration";
import { useShareModal } from "../../../hooks/useShareModal";

function Pipelines({ type }) {
  const [tableData, setTableData] = useState([]);
  const [openEtlOrTaskModal, setOpenEtlOrTaskModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [selectedPorD, setSelectedPorD] = useState({});
  const [tableLoading, setTableLoading] = useState(true);
  const { sessionDetails } = useSessionStore();
  const location = useLocation();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { clearFileHistory, isClearing: isClearingFileHistory } =
    useClearFileHistory();
  const [isEdit, setIsEdit] = useState(false);
  const [openFileHistoryModal, setOpenFileHistoryModal] = useState(false);
  const [openManageKeysModal, setOpenManageKeysModal] = useState(false);
  const [apiKeys, setApiKeys] = useState([]);
  const pipelineApiService = pipelineService();
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
    apiService: pipelineApiService,
    setSelectedItem: setSelectedPorD,
    setAlertDetails,
    handleException,
    refreshList: () =>
      getPipelineList(pagination.current, pagination.pageSize, searchTerm),
  });

  const initialFetchComplete = useInitialFetchCount(
    fetchCount,
    getPromptStudioCount
  );

  useEffect(() => {
    getPipelineList();
  }, [type]);

  const openAddModal = (edit) => {
    setIsEdit(edit);
    setOpenEtlOrTaskModal(true);
  };

  const getPipelineList = (page = 1, pageSize = 10, search = "") => {
    setTableLoading(true);
    const params = {
      type: type.toUpperCase(),
      page,
      page_size: pageSize,
    };
    if (search) {
      params.search = search;
    }
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/`,
      params,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        // Handle paginated response
        setTableData(data.results || data);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total: data.count ?? data.results?.length ?? data.length ?? 0,
        }));

        activateScrollRestore();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
        clearPendingScroll();
      })
      .finally(() => {
        setTableLoading(false);
      });
  };

  fetchListRef.current = getPipelineList;

  const handleSync = (params) => {
    const body = { ...params, pipeline_type: type.toUpperCase() };
    const pipelineId = params?.pipeline_id;
    const fieldsToUpdate = {
      last_run_status: "processing",
    };
    handleLoaderInTableData(fieldsToUpdate, pipelineId);

    handleSyncApiReq(body)
      .then((res) => {
        const data = res?.data?.pipeline;
        fieldsToUpdate.last_run_status = data?.last_run_status;
        fieldsToUpdate.last_run_time = data?.last_run_time;
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to sync."));
        fieldsToUpdate.last_run_status = "FAILURE";
        fieldsToUpdate.last_run_time = new Date().toISOString();
      })
      .finally(() => {
        handleLoaderInTableData(fieldsToUpdate, pipelineId);
      });
  };

  const handleLoaderInTableData = (updatedFields, pipelineId) => {
    // Use functional update to avoid stale closure issues
    setTableData((prevData) =>
      prevData.map((item) =>
        item.id === pipelineId ? { ...item, ...updatedFields } : item
      )
    );
  };

  const handleSyncApiReq = async (body) => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/execute/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const handleEnablePipeline = (value, id) => {
    // Optimistically update the UI immediately
    const fieldsToUpdate = { active: value };
    handleLoaderInTableData(fieldsToUpdate, id);

    const body = { active: value, pipeline_id: id };
    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/${id}/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    axiosPrivate(requestOptions).catch((err) => {
      // Revert optimistic update on failure
      handleLoaderInTableData({ active: !value }, id);
      setAlertDetails(handleException(err));
    });
  };

  const deletePipeline = () => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/${selectedPorD.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    axiosPrivate(requestOptions)
      .then(() => {
        setOpenDeleteModal(false);
        // Refresh with current pagination
        getPipelineList(pagination.current, pagination.pageSize, searchTerm);
        setAlertDetails({
          type: "success",
          content: "Pipeline Deleted Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const clearFileMarkers = async (workflowId) => {
    const id = workflowId || selectedPorD?.workflow_id;
    const success = await clearFileHistory(id);
    if (success && openDeleteModal) {
      setOpenDeleteModal(false);
    }
  };

  // Handlers for icon actions (top-right)
  const handleEditPipeline = () => {
    openAddModal(true);
  };

  const handleDeletePipeline = () => {
    setOpenDeleteModal(true);
  };

  // Handlers for expanded view actions
  const handleViewLogsPipeline = (pipeline) => {
    handleViewLogs(pipeline, setSelectedPorD);
  };

  const handleViewFileHistoryPipeline = (pipeline) => {
    if (!pipeline?.workflow_id) {
      setAlertDetails({
        type: "error",
        content: "Cannot view file history: Workflow ID not found",
      });
      return;
    }
    setSelectedPorD(pipeline);
    setOpenFileHistoryModal(true);
  };

  const handleClearFileHistoryPipeline = (pipeline) => {
    setSelectedPorD(pipeline);
    clearFileMarkers(pipeline.workflow_id);
  };

  const handleSyncNowPipeline = (pipeline) => {
    handleSync({ pipeline_id: pipeline.id });
  };

  const handleManageKeysPipeline = (pipeline) => {
    setSelectedPorD(pipeline);
    getApiKeys(
      pipelineApiService,
      pipeline.id,
      setApiKeys,
      setOpenManageKeysModal
    );
  };

  const handleSetupNotificationsPipeline = (pipeline) => {
    setSelectedPorD(pipeline);
    setOpenNotificationModal(true);
  };

  const handleDownloadPostmanPipeline = (pipeline) => {
    downloadPostmanCollection(pipelineApiService, pipeline.id);
  };

  // Card view configuration - no actionItems needed, all handlers passed directly
  const pipelineCardConfig = useMemo(
    () =>
      createPipelineCardConfig({
        setSelectedPorD,
        handleEnablePipeline,
        sessionDetails,
        location,
        // Icon actions
        onEdit: handleEditPipeline,
        onShare: handleShare,
        onDelete: handleDeletePipeline,
        // Expanded view actions
        onViewLogs: handleViewLogsPipeline,
        onViewFileHistory: handleViewFileHistoryPipeline,
        onClearFileHistory: handleClearFileHistoryPipeline,
        onSyncNow: handleSyncNowPipeline,
        onManageKeys: handleManageKeysPipeline,
        onSetupNotifications: handleSetupNotificationsPipeline,
        onDownloadPostman: handleDownloadPostmanPipeline,
        // Loading states
        isClearingFileHistory,
        // Pipeline type for status pill navigation
        pipelineType: type,
        // List context for scroll restoration on back navigation
        listContext: {
          page: pagination.current,
          pageSize: pagination.pageSize,
          searchTerm,
        },
      }),
    [
      sessionDetails,
      isClearingFileHistory,
      location,
      type,
      pagination.current,
      pagination.pageSize,
      searchTerm,
    ]
  );

  // Using the custom hook to manage modal state
  const { showModal, handleModalClose } = usePromptStudioModal(
    initialFetchComplete,
    isLoading,
    count
  );

  return (
    <div className="p-or-d-layout">
      {showModal && (
        <PromptStudioModal onClose={handleModalClose} showModal={showModal} />
      )}
      <Layout
        type={type}
        tableData={tableData}
        isTableLoading={tableLoading}
        openAddModal={openAddModal}
        cardConfig={pipelineCardConfig}
        listMode={true}
        scrollToId={scrollRestoreId}
        enableSearch={true}
        onSearch={handleSearch}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          onChange: handlePaginationChange,
        }}
      />
      {openEtlOrTaskModal && (
        <EtlTaskDeploy
          open={openEtlOrTaskModal}
          setOpen={setOpenEtlOrTaskModal}
          setTableData={setTableData}
          type={type}
          title={deploymentsStaticContent[type].addBtn}
          isEdit={isEdit}
          selectedRow={selectedPorD}
          setSelectedRow={setSelectedPorD}
        />
      )}
      <LogsModal
        open={openLogsModal}
        setOpen={setOpenLogsModal}
        logRecord={executionLogs}
        totalLogs={executionLogsTotalCount}
        fetchExecutionLogs={handleFetchLogs}
        loading={isFetchingLogs}
      />
      <DeleteModal
        open={openDeleteModal}
        setOpen={setOpenDeleteModal}
        deleteRecord={deletePipeline}
      />
      <ManageKeys
        isDialogOpen={openManageKeysModal}
        setDialogOpen={setOpenManageKeysModal}
        apiKeys={apiKeys}
        setApiKeys={setApiKeys}
        selectedApiRow={selectedPorD}
        apiService={pipelineApiService}
        type={deploymentApiTypes.pipeline}
      />
      <NotificationModal
        open={openNotificationModal}
        setOpen={setOpenNotificationModal}
        type={deploymentApiTypes.pipeline}
        id={selectedPorD?.id}
      />
      <FileHistoryModal
        open={openFileHistoryModal}
        setOpen={setOpenFileHistoryModal}
        workflowId={selectedPorD?.workflow_id}
        workflowName={selectedPorD?.pipeline_name}
      />
      {openShareModal && (
        <SharePermission
          open={openShareModal}
          setOpen={setOpenShareModal}
          adapter={selectedPorD}
          permissionEdit={true}
          loading={isLoadingShare}
          allUsers={Array.isArray(allUsers) ? allUsers : []}
          onApply={onShare}
          isSharableToOrg={true}
        />
      )}
    </div>
  );
}

Pipelines.propTypes = {
  type: PropTypes.string.isRequired,
};

export { Pipelines };
