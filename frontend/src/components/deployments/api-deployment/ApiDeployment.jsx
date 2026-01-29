import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import { deploymentApiTypes, displayURL } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { usePromptStudioStore } from "../../../store/prompt-studio-store";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import { CreateApiDeploymentModal } from "../create-api-deployment-modal/CreateApiDeploymentModal";
import { DeleteModal } from "../delete-modal/DeleteModal";
import { DisplayCode } from "../display-code/DisplayCode";
import { Layout } from "../layout/Layout";
import { ManageKeys } from "../manage-keys/ManageKeys";
import { PromptStudioModal } from "../../common/PromptStudioModal";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { apiDeploymentsService } from "./api-deployments-service";
import { createApiDeploymentCardConfig } from "./ApiDeploymentCardConfig.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { LogsModal } from "../../pipelines-or-deployments/log-modal/LogsModal.jsx";
import { fetchExecutionLogs } from "../../pipelines-or-deployments/log-modal/fetchExecutionLogs";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import usePipelineHelper from "../../../hooks/usePipelineHelper.js";
import { NotificationModal } from "../../pipelines-or-deployments/notification-modal/NotificationModal.jsx";
import { usePromptStudioService } from "../../api/prompt-studio-service";
import {
  useInitialFetchCount,
  usePromptStudioModal,
} from "../../../hooks/usePromptStudioFetchCount";

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
  const [openLogsModal, setOpenLogsModal] = useState(false);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [executionLogsTotalCount, setExecutionLogsTotalCount] = useState(0);
  const axiosPrivate = useAxiosPrivate();
  const { getApiKeys, downloadPostmanCollection, copyUrl } =
    usePipelineHelper();
  const [openNotificationModal, setOpenNotificationModal] = useState(false);
  const [openShareModal, setOpenShareModal] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [isLoadingShare, setIsLoadingShare] = useState(false);
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();

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
      selectedRow,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails,
      page,
      pageSize
    );
  };

  useEffect(() => {
    getApiDeploymentList();
    getWorkflows();
  }, []);

  useEffect(() => {
    setFilteredData(tableData);
  }, [tableData]);

  const handleSearch = (searchText) => {
    // Server-side search - pass to API
    getApiDeploymentList(1, pagination.pageSize, searchText?.trim() || "");
  };

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
        // Handle paginated response
        setTableData(data.results || data);
        setPagination((prev) => ({
          ...prev,
          current: page,
          pageSize,
          total:
            data.count || (data.results ? data.results.length : data.length),
        }));
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  };

  // Pagination change handler
  const handlePaginationChange = (page, pageSize) => {
    // Reset to page 1 if pageSize changed
    const newPage = pageSize !== pagination.pageSize ? 1 : page;
    getApiDeploymentList(newPage, pageSize);
  };

  const deleteApiDeployment = () => {
    apiDeploymentsApiService
      .deleteApiDeployment(selectedRow.id)
      .then((res) => {
        setOpenDeleteModal(false);
        // Refresh with current pagination
        getApiDeploymentList(pagination.current, pagination.pageSize);
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
    setIsTableLoading(true);
    record.is_active = !record?.is_active;
    apiDeploymentsApiService
      .updateApiDeployment(record)
      .then(() => {})
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  };

  const openAddModal = (edit) => {
    setIsEdit(edit);
    setOpenAddApiModal(true);
  };

  const handleShare = async () => {
    setIsLoadingShare(true);
    setOpenShareModal(true);
    // Fetch all users
    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        apiDeploymentsApiService.getAllUsers(),
        apiDeploymentsApiService.getSharedUsers(selectedRow.id),
      ]);

      const userList =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      // Pass the complete user list - SharePermission component will handle filtering
      setAllUsers(userList);

      // Update selected row with shared user info for the SharePermission component
      const updatedSelectedRow = {
        ...selectedRow,
        ...sharedUsersResponse.data,
      };
      setSelectedRow(updatedSelectedRow);
    } catch (err) {
      setAlertDetails(
        handleException(err, `Unable to fetch sharing information`)
      );
      setOpenShareModal(false);
    } finally {
      setIsLoadingShare(false);
    }
  };

  const onShare = (sharedUsers, api, shareWithEveryone) => {
    setIsLoadingShare(true);
    apiDeploymentsApiService
      .updateSharing(selectedRow.id, sharedUsers, shareWithEveryone)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Sharing permissions updated successfully",
        });
        setOpenShareModal(false);
        // Refresh with current pagination
        getApiDeploymentList(pagination.current, pagination.pageSize);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoadingShare(false);
      });
  };

  // Handlers for card view actions
  const handleEditDeployment = () => {
    openAddModal(true);
  };

  const handleShareDeployment = () => {
    handleShare();
  };

  const handleDeleteDeployment = () => {
    setOpenDeleteModal(true);
  };

  const handleViewLogsDeployment = (deployment) => {
    setSelectedRow(deployment);
    setOpenLogsModal(true);
    fetchExecutionLogs(
      axiosPrivate,
      handleException,
      sessionDetails,
      deployment,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails
    );
  };

  const handleManageKeysDeployment = (deployment) => {
    setSelectedRow(deployment);
    getApiKeys(
      apiDeploymentsApiService,
      deployment.id,
      setApiKeys,
      setOpenManageKeysModal
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
        onShare: handleShareDeployment,
        onDelete: handleDeleteDeployment,
        onViewLogs: handleViewLogsDeployment,
        onManageKeys: handleManageKeysDeployment,
        onSetupNotifications: handleSetupNotificationsDeployment,
        onCodeSnippets: handleCodeSnippetsDeployment,
        onDownloadPostman: handleDownloadPostmanDeployment,
      }),
    [sessionDetails, location]
  );

  // Using the custom hook to manage modal state
  const { showModal, handleModalClose } = usePromptStudioModal(
    initialFetchComplete,
    isLoading,
    count
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
