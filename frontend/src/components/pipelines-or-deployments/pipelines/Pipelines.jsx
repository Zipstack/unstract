import {
  ClearOutlined,
  DeleteOutlined,
  EllipsisOutlined,
  SyncOutlined,
  HighlightOutlined,
  FileSearchOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Image, Space, Switch, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import cronstrue from "cronstrue";

import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useSessionStore } from "../../../store/session-store.js";
import { Layout } from "../../deployments/layout/Layout.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { DeleteModal } from "../delete-modal/DeleteModal.jsx";
import { LogsModal } from "../log-modal/LogsModal.jsx";
import { EtlTaskDeploy } from "../etl-task-deploy/EtlTaskDeploy.jsx";
import "./Pipelines.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

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
  const [isEdit, setIsEdit] = useState(false);
  const [openLogsModal, setOpenLogsModal] = useState(false);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [executionLogsTotalCount, setExecutionLogsTotalCount] = useState(0);
  const { fetchExecutionLogs } = require("../log-modal/fetchExecutionLogs.js");

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
    const body = params;
    body["pipeline_type"] = type.toUpperCase();
    const pipelineId = params?.pipeline_id;
    const fieldsToUpdate = {
      last_run_status: "processing",
    };
    handleLoaderInTableData(fieldsToUpdate, pipelineId);

    handleSyncApiReq(body)
      .then((res) => {
        const data = res?.data?.pipeline;
        fieldsToUpdate["last_run_status"] = data?.last_run_status;
        fieldsToUpdate["last_run_time"] = data?.last_run_time;
        setAlertDetails({
          type: "success",
          content: "Pipeline Synced Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to sync."));
        const date = new Date();
        fieldsToUpdate["last_run_status"] = "FAILURE";
        fieldsToUpdate["last_run_time"] = date.toISOString();
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
        setAlertDetails({
          type: "success",
          content: value
            ? "Pipeline Enabled Successfully"
            : "Pipeline Disabled Successfully",
        });
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

  const clearCache = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${selectedPorD.workflow_id}/clear-cache/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    axiosPrivate(requestOptions)
      .then(() => {
        setOpenDeleteModal(false);
        setAlertDetails({
          type: "success",
          content: "Pipeline Cache Cleared Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const clearFileMarkers = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${selectedPorD.workflow_id}/clear-file-marker/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    axiosPrivate(requestOptions)
      .then(() => {
        setOpenDeleteModal(false);
        setAlertDetails({
          type: "success",
          content: "Pipeline File History Cleared Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const actionItems = [
    {
      key: "1",
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
      key: "2",
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
      key: "3",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => clearCache()}
        >
          <div>
            <ClearOutlined />
          </div>
          <div>
            <Typography.Text>Clear Cache</Typography.Text>
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
          onClick={() => clearFileMarkers()}
        >
          <div>
            <HighlightOutlined />
          </div>
          <div>
            <Typography.Text>Clear Processed File History</Typography.Text>
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
          onClick={() =>
            handleSync({
              pipeline_id: selectedPorD.id,
            })
          }
        >
          <div>
            <SyncOutlined />
          </div>
          <div>
            <Typography.Text>Sync Now</Typography.Text>
          </div>
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
            {cronstrue.toString(record?.cron_string)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "Enabled",
      key: "active",
      dataIndex: "active",
      align: "center",
      render: (_, record) => (
        <Switch
          checked={record.active}
          onChange={(e) => {
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
        >
          <EllipsisOutlined rotate={90} className="p-or-d-actions" />
        </Dropdown>
      ),
    },
  ];

  return (
    <div className="p-or-d-layout">
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
          title={deploymentsStaticContent[type].modalTitle}
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
    </div>
  );
}

Pipelines.propTypes = {
  type: PropTypes.string.isRequired,
};

export { Pipelines };
