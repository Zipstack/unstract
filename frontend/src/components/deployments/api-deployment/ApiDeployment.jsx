import {
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  KeyOutlined,
  CloudDownloadOutlined,
  FileSearchOutlined,
  NotificationOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Space, Switch, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

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
import { apiDeploymentsService } from "./api-deployments-service";
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
  const navigate = useNavigate();
  const apiDeploymentsApiService = apiDeploymentsService();
  const workflowApiService = workflowService();
  const [isTableLoading, setIsTableLoading] = useState(true);
  const [openAddApiModal, setOpenAddApiModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [openCodeModal, setOpenCodeModal] = useState(false);
  const [openManageKeysModal, setOpenManageKeysModal] = useState(false);
  const [selectedRow, setSelectedRow] = useState({});
  const [tableData, setTableData] = useState([]);
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
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();

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

  const columns = [
    {
      title: "API Name",
      key: "display_name",
      render: (_, record) => (
        <Typography.Text strong>{record?.display_name}</Typography.Text>
      ),
      align: "left",
    },
    {
      title: "Description",
      key: "description",
      render: (_, record) => <Space>{record?.description}</Space>,
      align: "left",
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
      title: "Workflow",
      key: "workflow_name",
      render: (_, record) => (
        <Tooltip title="view workflow">
          <Space
            className="workflowName"
            onClick={() =>
              navigate(
                `/${sessionDetails?.orgName}/workflows/${record?.workflow}`
              )
            }
          >
            {record?.workflow_name}
          </Space>
        </Tooltip>
      ),
      align: "left",
    },
    {
      title: "Enabled",
      key: "active",
      dataIndex: "active",
      align: "center",
      render: (_, record) => (
        <Switch
          size="small"
          checked={record.is_active}
          onChange={(e) => {
            updateStatus(record);
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
          trigger={["click"]}
          onOpenChange={() => setSelectedRow(record)}
        >
          <EllipsisOutlined className="cur-pointer" />
        </Dropdown>
      ),
    },
  ];

  useEffect(() => {
    getApiDeploymentList();
    getWorkflows();
  }, []);
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

  const getApiDeploymentList = () => {
    setIsTableLoading(true);

    apiDeploymentsApiService
      .getApiDeploymentsList()
      .then((res) => {
        setTableData(res?.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  };

  const deleteApiDeployment = () => {
    apiDeploymentsApiService
      .deleteApiDeployment(selectedRow.id)
      .then((res) => {
        setOpenDeleteModal(false);
        getApiDeploymentList();
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
      .then((res) => {
        setAlertDetails({
          type: "success",
          content: "Status updated successfully",
        });
      })
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

  const actionItems = [
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
              apiDeploymentsApiService,
              selectedRow?.id,
              setApiKeys,
              setOpenManageKeysModal
            )
          }
        >
          <div>
            <KeyOutlined />
          </div>
          <div>
            <Typography.Text>Manage Keys</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "3",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            downloadPostmanCollection(apiDeploymentsApiService, selectedRow?.id)
          }
        >
          <div>
            <CloudDownloadOutlined />
          </div>
          <div>
            <Typography.Text>Download Postman Collection</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "4",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenCodeModal(true)}
        >
          <div>
            <CodeOutlined />
          </div>
          <div>
            <Typography.Text>Code Snippets</Typography.Text>
          </div>
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
              selectedRow,
              setExecutionLogs,
              setExecutionLogsTotalCount,
              setAlertDetails
            );
          }}
        >
          <div>
            <FileSearchOutlined />
          </div>
          <div>
            <Typography.Text>View Logs</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "6",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenDeleteModal(true)}
        >
          <div>
            <DeleteOutlined />
          </div>
          <div>
            <Typography.Text>Delete</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "7",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenNotificationModal(true)}
        >
          <div>
            <NotificationOutlined />
          </div>
          <div>
            <Typography.Text>Setup Notifications</Typography.Text>
          </div>
        </Space>
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
    <>
      {showModal && (
        <PromptStudioModal onClose={handleModalClose} showModal={showModal} />
      )}
      <Layout
        type="api"
        columns={columns}
        tableData={tableData}
        isTableLoading={isTableLoading}
        openAddModal={openAddModal}
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
    </>
  );
}

export { ApiDeployment };
