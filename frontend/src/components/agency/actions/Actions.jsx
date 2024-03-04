import {
  ApiOutlined,
  ClearOutlined,
  DeploymentUnitOutlined,
  FastForwardOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  StepForwardOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Button, Divider, Space, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { StepIcon } from "../../../assets/index.js";
import { wfExecutionTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CreateApiDeploymentModal } from "../../deployments/create-api-deployment-modal/CreateApiDeploymentModal.jsx";
import { EtlTaskDeploy } from "../../pipelines-or-deployments/etl-task-deploy/EtlTaskDeploy.jsx";
import { SocketMessages } from "../../helpers/socket-messages/SocketMessages";
import FileUpload from "../file-upload/FileUpload.jsx";
import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import "./Actions.css";

function Actions({ statusBarMsg, initializeWfComp, stepLoader }) {
  const [logId, setLogId] = useState("");
  const [executionId, setExecutionId] = useState("");
  const [execType, setExecType] = useState("");
  const [stepExecType, setStepExecType] = useState("");
  const [openFileUploadModal, setOpenFileUploadModal] = useState(false);
  const [fileList, setFileList] = useState([]);
  const [wfExecutionParams, setWfExecutionParams] = useState([]);
  const [openAddApiModal, setOpenAddApiModal] = useState(false);
  const [apiOpsPresent, setApiOpsPresent] = useState(false);
  const [canAddTaskPipeline, setCanAddTaskPipeline] = useState(false);
  const [canAddETLPipeline, setCanAddETAPipeline] = useState(false);
  const [openAddTaskModal, setOpenAddTaskModal] = useState(false);
  const [openAddETLModal, setOpenAddETLModal] = useState(false);

  const {
    details,
    isLoading,
    loadingType,
    updateWorkflow,
    source,
    destination,
  } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    setApiOpsPresent(source?.connection_type === "API");
  }, [source]);

  useEffect(() => {
    setCanAddTaskPipeline(destination?.connection_type === "FILESYSTEM");
    setCanAddETAPipeline(destination?.connection_type === "DATABASE");
  }, [destination]);

  useEffect(() => {
    if (stepExecType === wfExecutionTypes[1]) {
      setStepExecType("");
    }
  }, [stepLoader]);

  const getInputFile = (isInitial, isStepExecution, executionAction) => {
    setWfExecutionParams([isInitial, isStepExecution, executionAction]);
    setFileList([]);
    setOpenFileUploadModal(true);
  };

  const handleInitialExecution = async (
    body,
    isStepExecution,
    executionAction
  ) => {
    initializeWfComp();
    if (isStepExecution) {
      setExecType("STEP");
      body["execution_action"] = wfExecutionTypes[0];
    } else {
      setExecType("NORMAL");
    }

    const loadingStatus = {
      isLoading: true,
      loadingType: "EXECUTE",
    };
    updateWorkflow(loadingStatus);

    try {
      const initialRes = await handleWfExecutionApi(body);
      const execIdValue = initialRes?.data?.execution_id;
      const logIdValue = initialRes?.data?.log_id;

      setExecutionId(execIdValue);
      setLogId(logIdValue);
      body["execution_id"] = execIdValue;
      if (isStepExecution) {
        body["execution_action"] = wfExecutionTypes[executionAction];
      }
      const wfExecRes = await handleWfExecutionApi(body);
      const data = wfExecRes?.data;
      if (data?.execution_status === "ERROR") {
        setAlertDetails({
          type: "error",
          content: data?.error,
        });
      }
    } catch (err) {
      const errorDetail =
        err?.response?.data?.errors?.length > 0
          ? err.response.data.errors[0].detail
          : "Something went wrong";
      setAlertDetails({
        type: "error",
        content: errorDetail,
      });
    } finally {
      handleClearStates();
      loadingStatus["isLoading"] = false;
      loadingStatus["loadingType"] = "";
      updateWorkflow(loadingStatus);
    }
  };

  const handleWfExecution = async (
    isInitial,
    isStepExecution,
    executionAction
  ) => {
    const workflowId = details?.id;

    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Invalid workflow id",
      });
      return;
    }

    const body = {
      workflow_id: workflowId,
    };

    if (isInitial) {
      await handleInitialExecution(body, isStepExecution, executionAction);
    } else {
      setStepExecType(wfExecutionTypes[executionAction]);
      body["execution_id"] = executionId;
      body["execution_action"] = wfExecutionTypes[executionAction];

      handleWfExecutionApi(body)
        .then(() => {})
        .catch((err) => {
          const errorDetail =
            err?.response?.data?.errors?.length > 0
              ? err.response.data.errors[0].detail
              : "Something went wrong";
          setAlertDetails({
            type: "error",
            content: errorDetail,
          });
        });
    }
  };

  const getRequestBody = (body) => {
    const formData = new FormData();
    fileList.forEach((file) => {
      formData.append("files", file);
    });
    formData.append("workflow_id", body["workflow_id"]);
    formData.append("execution_id", body["execution_id"]);
    if (body["execution_action"]) {
      formData.append("execution_action", body["execution_action"]);
    }
    return formData;
  };

  const shouldIncludeFile = (body) => {
    return body["execution_id"] && body["execution_id"].length > 0;
  };

  const handleWfExecutionApi = async (body) => {
    let header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };
    if (shouldIncludeFile(body) && apiOpsPresent && fileList.length > 0) {
      body = getRequestBody(body);
      header = {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "multipart/form-data",
      };
    }
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/execute/`,
      headers: header,
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const handleDisable = (wfExecTypeIndex) => {
    if (!isLoading) {
      return (
        wfExecTypeIndex === 1 || wfExecTypeIndex === 2 || wfExecTypeIndex === 3
      );
    }

    if (loadingType === "GENERATE") {
      return true;
    }

    // We can assume that the "loadingType" value is always going to be "EXECUTE" from here onwards.
    if (execType === "NORMAL") {
      return true;
    }

    // We can assume that the "execType" value is always going to be "STEP" from here onwards.
    if (wfExecTypeIndex === 0 || wfExecTypeIndex === 4) {
      return true;
    }

    if (
      stepExecType === wfExecutionTypes[1] ||
      stepExecType === wfExecutionTypes[2]
    ) {
      return true;
    }

    return stepExecType === wfExecutionTypes[wfExecTypeIndex];
  };

  const handleClearStates = () => {
    setExecType("");
    setStepExecType("");
    setExecutionId("");
  };

  const createDeployment = (type) => {
    const workflowId = details?.id;
    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Invalid workflow id",
      });
      return;
    }
    if (type === "API") {
      setOpenAddApiModal(true);
    }
    if (type === "TASK") {
      setOpenAddTaskModal(true);
    }
    if (type === "ETL") {
      setOpenAddETLModal(true);
    }
  };

  const handleClearCache = () => {
    const workflowId = details?.id;

    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Invalid workflow id",
      });
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${workflowId}/clear-cache/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const msg = res?.data;
        setAlertDetails({
          type: "success",
          content: msg,
        });
      })
      .catch((err) => {
        const msg = err?.response?.data || "Failed to clear cache.";
        setAlertDetails({
          type: "error",
          content: msg,
        });
      });
  };

  const handleClearFileMarker = () => {
    const workflowId = details?.id;

    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Invalid workflow id",
      });
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${workflowId}/clear-file-marker/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const msg = res?.data;
        setAlertDetails({
          type: "success",
          content: msg,
        });
      })
      .catch((err) => {
        const msg = err?.response?.data || "Failed to clear file marker.";
        setAlertDetails({
          type: "error",
          content: msg,
        });
      });
  };

  return (
    <>
      <div className="actions-container">
        <Space direction="horizontal" className="display-flex-left">
          <Tooltip title="Run Workflow">
            <Button
              onClick={() =>
                apiOpsPresent
                  ? getInputFile(true, false, 4)
                  : handleWfExecution(true, false, 4)
              }
              disabled={handleDisable(4)}
              loading={execType === "NORMAL"}
            >
              <PlayCircleOutlined />
            </Button>
          </Tooltip>
          <Divider type="vertical" />
          <Tooltip title="Start step execution">
            <Button
              onClick={() =>
                apiOpsPresent
                  ? getInputFile(true, true, 0)
                  : handleWfExecution(true, true, 0)
              }
              disabled={handleDisable(0)}
              loading={execType === "STEP"}
            >
              <StepIcon className="step-icon" />
            </Button>
          </Tooltip>
          <Tooltip title="Next step">
            <Button
              onClick={() => handleWfExecution(false, true, 1)}
              disabled={handleDisable(1)}
              loading={stepExecType === wfExecutionTypes[1]}
            >
              <StepForwardOutlined />
            </Button>
          </Tooltip>
          <Tooltip title="Execute remaining steps">
            <Button
              onClick={() => handleWfExecution(false, true, 3)}
              disabled={handleDisable(3)}
              loading={stepExecType === wfExecutionTypes[3]}
            >
              <FastForwardOutlined />
            </Button>
          </Tooltip>
          <Tooltip title="Stop execution">
            <Button
              onClick={() => handleWfExecution(false, true, 2)}
              disabled={handleDisable(2)}
              loading={stepExecType === wfExecutionTypes[2]}
            >
              <StopOutlined />
            </Button>
          </Tooltip>
          <Divider type="vertical" />
          <Tooltip title="Clear Cache">
            <Button disabled={isLoading} onClick={handleClearCache}>
              <ClearOutlined />
            </Button>
          </Tooltip>
          <Tooltip title="Clear File Marker">
            <Button disabled={isLoading} onClick={handleClearFileMarker}>
              <HistoryOutlined />
            </Button>
          </Tooltip>
          <Divider type="vertical" />
          <Tooltip title="Deploy as ETL Pipeline">
            <Button
              disabled={!canAddETLPipeline}
              onClick={() => createDeployment("ETL")}
            >
              <ApiOutlined />
            </Button>
          </Tooltip>
          <Tooltip title="Deploy as Task Pipeline">
            <Button
              disabled={!canAddTaskPipeline}
              onClick={() => createDeployment("TASK")}
            >
              <DeploymentUnitOutlined />
            </Button>
          </Tooltip>
          <Tooltip title="Deploy as API">
            <Button
              disabled={!apiOpsPresent}
              onClick={() => createDeployment("API")}
            >
              <ApiOutlined />
            </Button>
          </Tooltip>
        </Space>
        <div className="status-bar">
          <Typography.Text>{statusBarMsg}</Typography.Text>
        </div>
      </div>
      {openFileUploadModal && (
        <FileUpload
          open={openFileUploadModal}
          setFileList={setFileList}
          fileList={fileList}
          setOpen={setOpenFileUploadModal}
          wfExecutionParams={wfExecutionParams}
          continueWfExecution={handleWfExecution}
        />
      )}
      {openAddApiModal && (
        <CreateApiDeploymentModal
          open={openAddApiModal}
          setOpen={setOpenAddApiModal}
          isEdit={false}
          workflowId={details?.id}
        />
      )}
      {openAddTaskModal && (
        <EtlTaskDeploy
          open={openAddTaskModal}
          setOpen={setOpenAddTaskModal}
          type="task"
          title={deploymentsStaticContent["task"].modalTitle}
        />
      )}
      {openAddETLModal && (
        <EtlTaskDeploy
          open={openAddETLModal}
          setOpen={setOpenAddETLModal}
          type="etl"
          title={deploymentsStaticContent["etl"].modalTitle}
        />
      )}
      <SocketMessages logId={logId} />
    </>
  );
}

Actions.propTypes = {
  statusBarMsg: PropTypes.string,
  initializeWfComp: PropTypes.func.isRequired,
  stepLoader: PropTypes.bool.isRequired,
};

export { Actions };
