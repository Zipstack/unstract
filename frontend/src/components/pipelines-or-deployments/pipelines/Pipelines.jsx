import {
  DeleteOutlined,
  EllipsisOutlined,
  SyncOutlined,
  HighlightOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  NotificationOutlined,
  EditOutlined,
  KeyOutlined,
  CloudDownloadOutlined,
  CopyOutlined,
  LoadingOutlined,
  ShareAltOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import {
  Button,
  Dropdown,
  Image,
  Space,
  Switch,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import cronstrue from "cronstrue";

import {
  deploymentApiTypes,
  deploymentsStaticContent,
  displayURL,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useSessionStore } from "../../../store/session-store.js";
import { Layout } from "../../deployments/layout/Layout.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
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
import { CoOwnerManagement } from "../../widgets/co-owner-management/CoOwnerManagement";

function Pipelines({ type }) {
  const [tableData, setTableData] = useState([]);
  const [openEtlOrTaskModal, setOpenEtlOrTaskModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [selectedPorD, setSelectedPorD] = useState({});
  const [tableLoading, setTableLoading] = useState(true);
  const { sessionDetails } = useSessionStore();
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
  const { fetchExecutionLogs } = require("../log-modal/fetchExecutionLogs.js");
  const [openManageKeysModal, setOpenManageKeysModal] = useState(false);
  const [apiKeys, setApiKeys] = useState([]);
  const pipelineApiService = pipelineService();
  const { getApiKeys, downloadPostmanCollection, copyUrl } =
    usePipelineHelper();
  const [openNotificationModal, setOpenNotificationModal] = useState(false);
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();
  // Sharing state
  const [openShareModal, setOpenShareModal] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [isLoadingShare, setIsLoadingShare] = useState(false);
  // Co-owner state
  const [coOwnerOpen, setCoOwnerOpen] = useState(false);
  const [coOwnerData, setCoOwnerData] = useState({
    coOwners: [],
    createdBy: null,
  });
  const [coOwnerLoading, setCoOwnerLoading] = useState(false);
  const [coOwnerAllUsers, setCoOwnerAllUsers] = useState([]);

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

  const openAddModal = (edit) => {
    setIsEdit(edit);
    setOpenEtlOrTaskModal(true);
  };

  const getPipelineList = () => {
    setTableLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/pipeline/?type=${type.toUpperCase()}`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        setTableData(res?.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setTableLoading(false);
      });
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

  const handleStatusRefresh = (pipelineId) => {
    const fieldsToUpdate = {
      last_run_status: "processing",
    };
    handleLoaderInTableData(fieldsToUpdate, pipelineId);

    getPipelineData(pipelineId)
      .then((res) => {
        const data = res?.data;
        fieldsToUpdate["last_run_status"] = data?.last_run_status;
        fieldsToUpdate["last_run_time"] = data?.last_run_time;
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, `Failed to update pipeline status.`)
        );
        const date = new Date();
        fieldsToUpdate["last_run_status"] = "FAILURE";
        fieldsToUpdate["last_run_time"] = date.toISOString();
      })
      .finally(() => {
        handleLoaderInTableData(fieldsToUpdate, pipelineId);
      });
  };

  const handleLoaderInTableData = (updatedFields, pipelineId) => {
    const filteredData = tableData.map((item) => {
      if (item.id === pipelineId) {
        return { ...item, ...updatedFields };
      }
      return item;
    });
    setTableData(filteredData);
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
    axiosPrivate(requestOptions)
      .then(() => {
        getPipelineList();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {});
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
        getPipelineList();
        setAlertDetails({
          type: "success",
          content: "Pipeline Deleted Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const getPipelineData = (pipelineId) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/${pipelineId}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const clearFileMarkers = async () => {
    const workflowId = selectedPorD?.workflow_id;
    const success = await clearFileHistory(workflowId);
    if (success && openDeleteModal) {
      setOpenDeleteModal(false);
    }
  };

  const handleShare = async () => {
    setIsLoadingShare(true);
    // Fetch all users and shared users first, then open modal
    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        pipelineApiService.getAllUsers(),
        pipelineApiService.getSharedUsers(selectedPorD.id),
      ]);

      // Extract members array from the response and map to the required format
      const userList =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      const sharedUsersList = sharedUsersResponse.data?.shared_users || [];

      // Set shared_users property on selectedPorD for SharePermission component
      setSelectedPorD({
        ...selectedPorD,
        shared_users: Array.isArray(sharedUsersList) ? sharedUsersList : [],
      });

      setAllUsers(userList);

      // Only open modal after data is loaded
      setOpenShareModal(true);
    } catch (error) {
      setAlertDetails(handleException(error));
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
        // Refresh pipeline list to show updated ownership
        getPipelineList();
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

  const handleCoOwner = async (record) => {
    const row = record || selectedPorD;
    setCoOwnerLoading(true);
    setCoOwnerOpen(true);

    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        pipelineApiService.getAllUsers(),
        pipelineApiService.getSharedUsers(row.id),
      ]);

      const userList =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      setCoOwnerAllUsers(userList);
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
      const res = await pipelineApiService.getSharedUsers(resourceId);
      setCoOwnerData({
        coOwners: res.data?.co_owners || [],
        createdBy: res.data?.created_by || null,
      });
    } catch (err) {
      if (err?.response?.status === 404) {
        setCoOwnerOpen(false);
        getPipelineList();
        setAlertDetails({
          type: "error",
          content:
            "This resource is no longer accessible. It may have been removed or your access has been revoked.",
        });
        return;
      }
      setAlertDetails(handleException(err, "Unable to refresh co-owner data"));
    }
  };

  const onAddCoOwner = async (resourceId, userId) => {
    try {
      await pipelineApiService.addCoOwner(resourceId, userId);
      setAlertDetails({
        type: "success",
        content: "Co-owner added successfully",
      });
      await refreshCoOwnerData(resourceId);
      getPipelineList();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to add co-owner"));
    }
  };

  const onRemoveCoOwner = async (resourceId, userId) => {
    try {
      await pipelineApiService.removeCoOwner(resourceId, userId);
      setAlertDetails({
        type: "success",
        content: "Co-owner removed successfully",
      });
      await refreshCoOwnerData(resourceId);
      getPipelineList();
    } catch (err) {
      setAlertDetails(handleException(err, "Unable to remove co-owner"));
    }
  };

  const actionItems = [
    // Configuration Section
    {
      key: "1",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => openAddModal(true)}
        >
          <div>
            <EditOutlined />
          </div>
          <div>
            <Typography.Text>Edit</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "2",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            getApiKeys(
              pipelineApiService,
              selectedPorD?.id,
              setApiKeys,
              setOpenManageKeysModal
            )
          }
        >
          <KeyOutlined />
          <Typography.Text>Manage Keys</Typography.Text>
        </Space>
      ),
    },
    {
      key: "3",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenNotificationModal(true)}
        >
          <NotificationOutlined />
          <Typography.Text>Setup Notifications</Typography.Text>
        </Space>
      ),
    },
    {
      key: "share",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={handleShare}
        >
          <ShareAltOutlined />
          <Typography.Text>Share</Typography.Text>
        </Space>
      ),
    },
    {
      key: "divider-config",
      type: "divider",
    },
    // Operation Section
    {
      key: "4",
      label: (
        <Space
          direction="horizontal"
          className={`action-items ${
            isClearingFileHistory
              ? "action-item-disabled"
              : "action-item-enabled"
          }`}
          onClick={() =>
            !isClearingFileHistory &&
            handleSync({
              pipeline_id: selectedPorD.id,
            })
          }
        >
          <SyncOutlined />
          <Typography.Text>Sync Now</Typography.Text>
        </Space>
      ),
    },
    {
      key: "5",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => {
            setOpenLogsModal(true);
            fetchExecutionLogs(
              axiosPrivate,
              handleException,
              sessionDetails,
              selectedPorD,
              setExecutionLogs,
              setExecutionLogsTotalCount,
              setAlertDetails
            );
          }}
        >
          <FileSearchOutlined />
          <Typography.Text>View Logs</Typography.Text>
        </Space>
      ),
    },
    {
      key: "view-file-history",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => {
            if (!selectedPorD?.workflow_id) {
              setAlertDetails({
                type: "error",
                content: "Cannot view file history: Workflow ID not found",
              });
              return;
            }

            setOpenFileHistoryModal(true);
          }}
        >
          <HistoryOutlined />
          <Typography.Text>View File History</Typography.Text>
        </Space>
      ),
    },
    {
      key: "divider-operation",
      type: "divider",
    },
    // Developer related Section
    {
      key: "6",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            downloadPostmanCollection(pipelineApiService, selectedPorD?.id)
          }
        >
          <CloudDownloadOutlined />
          <Typography.Text>Download Postman Collection</Typography.Text>
        </Space>
      ),
    },
    {
      key: "divider-dev-related",
      type: "divider",
    },
    // Delete related section
    {
      key: "7",
      label: (
        <Space
          direction="horizontal"
          className={`action-items ${
            isClearingFileHistory
              ? "action-item-disabled"
              : "action-item-enabled"
          }`}
          onClick={() => !isClearingFileHistory && clearFileMarkers()}
        >
          {isClearingFileHistory ? <LoadingOutlined /> : <HighlightOutlined />}
          <Typography.Text>Clear Processed File History</Typography.Text>
        </Space>
      ),
    },
    {
      key: "8",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenDeleteModal(true)}
        >
          <DeleteOutlined />
          <Typography.Text>Delete</Typography.Text>
        </Space>
      ),
    },
  ];

  const columns = [
    {
      title: "Source",
      render: (_, record) => (
        <div>
          <div>
            <Image src={record?.source_icon} preview={false} width={30} />
          </div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.source_name}
          </Typography.Text>
        </div>
      ),
      key: "source",
      align: "center",
    },
    {
      title: "Pipeline",
      key: "pipeline_name",
      render: (_, record) => (
        <>
          <Typography.Text strong>{record?.pipeline_name}</Typography.Text>
          <br />
          <Typography.Text type="secondary" className="p-or-d-typography">
            from {record?.workflow_name}
          </Typography.Text>
        </>
      ),
      align: "center",
    },
    {
      title: "Destination",
      render: (_, record) => (
        <div>
          <div>
            <Image src={record?.destination_icon} preview={false} width={30} />
          </div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.destination_name}
          </Typography.Text>
        </div>
      ),
      key: "destination",
      align: "center",
    },
    {
      title: "API Endpoint",
      key: "api_endpoint",
      render: (_, record) => (
        <Space direction="horizontal" className="display-flex-space-between">
          <div>
            <Typography.Text>
              {displayURL(record?.api_endpoint)}
            </Typography.Text>
          </div>
          <div>
            <Tooltip title="click to copy">
              <Button
                size="small"
                onClick={() => copyUrl(record?.api_endpoint)}
              >
                <CopyOutlined />
              </Button>
            </Tooltip>
          </div>
        </Space>
      ),
      align: "left",
    },
    {
      title: "Status of Previous Run",
      dataIndex: "last_run_status",
      key: "last_run_status",
      align: "center",
      render: (_, record) => (
        <>
          {record.last_run_status === "processing" ? (
            <SpinnerLoader />
          ) : (
            <Space>
              <Typography.Text className="p-or-d-typography" strong>
                {record?.last_run_status}
              </Typography.Text>
              <Button
                icon={<ReloadOutlined />}
                type="text"
                size="small"
                onClick={() => handleStatusRefresh(record?.id)}
              />
            </Space>
          )}
        </>
      ),
    },
    {
      title: "Previous Run At",
      key: "last_run_time",
      dataIndex: "last_run_time",
      align: "center",
      render: (_, record) => (
        <div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.last_run_time}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "Frequency",
      key: "last_run_time",
      dataIndex: "last_run_time",
      align: "center",
      render: (_, record) => (
        <div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.cron_string && cronstrue.toString(record?.cron_string)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "Owner",
      dataIndex: "created_by_email",
      key: "created_by_email",
      align: "center",
      render: (email, record) => {
        const isOwner = record?.is_owner;
        return (
          <Tooltip title="Manage Co-Owners">
            <span
              style={{
                cursor: "pointer",
                color: "#1890ff",
                textDecoration: "underline",
                textDecorationStyle: "dotted",
              }}
              onClick={() => {
                setSelectedPorD(record);
                handleCoOwner(record);
              }}
            >
              {isOwner ? "You" : email?.split("@")[0] || "Unknown"}
              {record?.co_owners_count > 1 && ` +${record.co_owners_count - 1}`}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: "Enabled",
      key: "active",
      dataIndex: "active",
      align: "center",
      render: (_, record) => (
        <Switch
          checked={record.active}
          onChange={() => {
            handleEnablePipeline(!record.active, record.id);
          }}
        />
      ),
    },
    {
      title: "Actions",
      key: "pipeline_id",
      align: "center",
      render: (_, record) => (
        <Dropdown
          menu={{ items: actionItems }}
          placement="bottomLeft"
          onOpenChange={() => setSelectedPorD(record)}
          trigger={["click"]}
        >
          <EllipsisOutlined className="p-or-d-actions cur-pointer" />
        </Dropdown>
      ),
    },
  ];

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
        columns={columns}
        tableData={tableData}
        isTableLoading={tableLoading}
        openAddModal={openAddModal}
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
      {coOwnerOpen && (
        <CoOwnerManagement
          open={coOwnerOpen}
          setOpen={setCoOwnerOpen}
          resourceId={selectedPorD?.id}
          resourceType="Pipeline"
          allUsers={coOwnerAllUsers}
          coOwners={coOwnerData.coOwners}
          createdBy={coOwnerData.createdBy}
          loading={coOwnerLoading}
          onAddCoOwner={onAddCoOwner}
          onRemoveCoOwner={onRemoveCoOwner}
        />
      )}
    </div>
  );
}

Pipelines.propTypes = {
  type: PropTypes.string.isRequired,
};

export { Pipelines };
