import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";
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

function Pipelines({ type }) {
  const [tableData, setTableData] = useState([]);
  const [openEtlOrTaskModal, setOpenEtlOrTaskModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [selectedPorD, setSelectedPorD] = useState({});
  const [tableLoading, setTableLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const { sessionDetails } = useSessionStore();
  const location = useLocation();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { clearFileHistory, isClearing: isClearingFileHistory } =
    useClearFileHistory();
  const [isEdit, setIsEdit] = useState(false);
  const [openLogsModal, setOpenLogsModal] = useState(false);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [executionLogsTotalCount, setExecutionLogsTotalCount] = useState(0);
  const [openFileHistoryModal, setOpenFileHistoryModal] = useState(false);
  const { fetchExecutionLogs } = require("../log-modal/fetchExecutionLogs");
  const [openManageKeysModal, setOpenManageKeysModal] = useState(false);
  const [apiKeys, setApiKeys] = useState([]);
  const pipelineApiService = pipelineService();
  const { getApiKeys, downloadPostmanCollection } = usePipelineHelper();
  const [openNotificationModal, setOpenNotificationModal] = useState(false);
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();
  // Sharing state
  const [openShareModal, setOpenShareModal] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [isLoadingShare, setIsLoadingShare] = useState(false);

  // Scroll restoration state
  const [scrollRestoreId, setScrollRestoreId] = useState(null);

  // Pagination state
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const initialFetchComplete = useInitialFetchCount(
    fetchCount,
    getPromptStudioCount
  );

  const handleFetchLogs = (page, pageSize) => {
    fetchExecutionLogs(
      axiosPrivate,
      handleException,
      sessionDetails,
      selectedPorD,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails,
      page,
      pageSize
    );
  };

  useEffect(() => {
    getPipelineList();
  }, [type]);

  // Handle scroll restoration and list context from navigation
  useEffect(() => {
    if (location.state?.scrollToCardId) {
      // Restore pagination and search state if available
      const { page, pageSize, searchTerm: savedSearch } = location.state;
      if (page || pageSize || savedSearch !== undefined) {
        const restoredPage = page || 1;
        const restoredPageSize = pageSize || 10;
        const restoredSearch = savedSearch || "";
        setSearchTerm(restoredSearch);
        setPagination((prev) => ({
          ...prev,
          current: restoredPage,
          pageSize: restoredPageSize,
        }));
        // Fetch with restored context before scrolling
        getPipelineList(restoredPage, restoredPageSize, restoredSearch);
      }
      setScrollRestoreId(location.state.scrollToCardId);
      // Clear after a short delay to prevent re-triggering
      const timer = setTimeout(() => {
        setScrollRestoreId(null);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [location.state?.scrollToCardId]);

  const handleSearch = (searchText, _setSearchList) => {
    const term = searchText?.trim() || "";
    setSearchTerm(term);
    getPipelineList(1, pagination.pageSize, term);
  };

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
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setTableLoading(false);
      });
  };

  // Pagination change handler
  const handlePaginationChange = (page, pageSize) => {
    // Reset to page 1 if pageSize changed
    const newPage = pageSize === pagination.pageSize ? page : 1;
    getPipelineList(newPage, pageSize, searchTerm);
  };

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

  const handleShare = async (pipeline) => {
    // Use passed pipeline directly to avoid stale state issues
    const pipelineToShare = pipeline || selectedPorD;
    setIsLoadingShare(true);
    // Fetch all users and shared users first, then open modal
    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        pipelineApiService.getAllUsers(),
        pipelineApiService.getSharedUsers(pipelineToShare.id),
      ]);

      // Robust response handling - check multiple possible structures
      let userList = [];
      const responseData = usersResponse?.data;
      if (Array.isArray(responseData)) {
        userList = responseData.map((user) => ({
          id: user.id,
          email: user.email,
        }));
      } else if (responseData?.members && Array.isArray(responseData.members)) {
        userList = responseData.members.map((member) => ({
          id: member.id,
          email: member.email,
        }));
      } else if (responseData?.users && Array.isArray(responseData.users)) {
        userList = responseData.users.map((user) => ({
          id: user.id,
          email: user.email,
        }));
      }

      const sharedUsersList = sharedUsersResponse.data?.shared_users || [];

      // Set shared_users property on selectedPorD for SharePermission component
      setSelectedPorD({
        ...pipelineToShare,
        shared_users: Array.isArray(sharedUsersList) ? sharedUsersList : [],
      });

      setAllUsers(userList);

      // Only open modal after data is loaded
      setOpenShareModal(true);
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to load sharing data"));
      // Ensure allUsers is always an array even on error
      setAllUsers([]);
    } finally {
      setIsLoadingShare(false);
    }
  };

  const onShare = (sharedUsers, _, shareWithEveryone) => {
    setIsLoadingShare(true);
    // sharedUsers is already an array of user IDs from SharePermission component

    pipelineApiService
      .updateSharing(selectedPorD.id, sharedUsers, shareWithEveryone)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Sharing permissions updated successfully",
        });
        setOpenShareModal(false);
        // Refresh with current pagination
        getPipelineList(pagination.current, pagination.pageSize, searchTerm);
      })
      .catch((error) => {
        setAlertDetails(
          handleException(error, "Failed to update sharing settings")
        );
      })
      .finally(() => {
        setIsLoadingShare(false);
      });
  };

  // Handlers for icon actions (top-right)
  const handleEditPipeline = () => {
    openAddModal(true);
  };

  const handleSharePipeline = (pipeline) => {
    handleShare(pipeline);
  };

  const handleDeletePipeline = () => {
    setOpenDeleteModal(true);
  };

  // Handlers for expanded view actions
  const handleViewLogsPipeline = (pipeline) => {
    setSelectedPorD(pipeline);
    setOpenLogsModal(true);
    fetchExecutionLogs(
      axiosPrivate,
      handleException,
      sessionDetails,
      pipeline,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails
    );
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
        onShare: handleSharePipeline,
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
