import { Button, Row, Col, Typography, Progress, Dropdown, Select } from "antd";
import { LeftOutlined, MoreOutlined, BugOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import { Actions } from "../actions/Actions";
import "./Agency.css";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { SidePanel } from "../side-panel/SidePanel";
import { PageTitle } from "../../widgets/page-title/PageTitle";
import { WorkflowCard } from "../workflow-card/WorkflowCard";
import { sourceTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { CreateApiDeploymentModal } from "../../deployments/create-api-deployment-modal/CreateApiDeploymentModal.jsx";
import { EtlTaskDeploy } from "../../pipelines-or-deployments/etl-task-deploy/EtlTaskDeploy.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

function Agency() {
  const [steps, setSteps] = useState([]);
  // eslint-disable-next-line no-unused-vars
  const [inputMd, setInputMd] = useState("");
  // eslint-disable-next-line no-unused-vars
  const [outputMd, setOutputMd] = useState("");
  const [statusBarMsg, setStatusBarMsg] = useState("");
  const [sourceMsg, setSourceMsg] = useState("");
  const [destinationMsg, setDestinationMsg] = useState("");
  const { message, setDefault } = useSocketMessagesStore();
  const workflowStore = useWorkflowStore();
  const {
    details,
    loadingType,
    projectName,
    source,
    destination,
    projectId,
    updateWorkflow,
  } = workflowStore;
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const prompt = details?.prompt_text;
  // eslint-disable-next-line no-unused-vars
  const [activeToolId, setActiveToolId] = useState("");
  const [prevLoadingType, setPrevLoadingType] = useState("");
  const [isUpdateSteps, setIsUpdateSteps] = useState(false);
  const [stepLoader, setStepLoader] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [promptStudioProjects, setPromptStudioProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [selectedDeploymentType, setSelectedDeploymentType] = useState(null);
  const [openAddApiModal, setOpenAddApiModal] = useState(false);
  const [openAddETLModal, setOpenAddETLModal] = useState(false);
  const [openAddTaskModal, setOpenAddTaskModal] = useState(false);
  const { setPostHogCustomEvent } = usePostHogEvents();

  useEffect(() => {
    getWfEndpointDetails();
    canUpdateWorkflow();
    getPromptStudioProjects();
  }, []);

  useEffect(() => {
    if (prevLoadingType !== "EXECUTE") {
      setIsUpdateSteps(true);
    }

    setPrevLoadingType(loadingType);
  }, [workflowStore]);

  useEffect(() => {
    if (!isUpdateSteps) {
      return;
    }
    setToolInstances();
    setIsUpdateSteps(false);
  }, [isUpdateSteps, prompt]);

  const getWfEndpointDetails = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${projectId}/endpoint/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];
        const sourceDetails = data.find(
          (item) => item?.endpoint_type === "SOURCE"
        );
        const destDetails = data.find(
          (item) => item?.endpoint_type === "DESTINATION"
        );
        const body = {
          source: sourceDetails,
          destination: destDetails,
        };
        updateWorkflow(body);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to get endpoints"));
      });
  };

  const canUpdateWorkflow = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${projectId}/can-update/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        const body = {
          allowChangeEndpoint: data?.can_update,
        };
        updateWorkflow(body);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to get can update status")
        );
      });
  };

  const getPromptStudioProjects = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];
        setPromptStudioProjects(data);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to get prompt studio projects")
        );
      });
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

  const handleDeployBtnClick = (deployType) => {
    createDeployment(deployType);

    try {
      const posthogWfDeploymentEventText = {
        API: "wf_deploy_as_api_clicked",
        ETL: "wf_deploy_as_etl_clicked",
        TASK: "wf_deploy_as_task_clicked",
      };

      setPostHogCustomEvent(posthogWfDeploymentEventText[deployType], {
        info: `Clicked on 'Deploy as ${deployType}' button`,
        workflow_name: projectName,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const handleDeploymentTypeChange = (value) => {
    setSelectedDeploymentType(value);
    if (value) {
      handleDeployBtnClick(value);
    }
  };

  const setToolInstances = () => {
    const toolInstances = [...(details?.tool_instances || [])];
    setSteps(toolInstances);
  };

  const initializeWfComp = () => {
    setToolInstances();
    setActiveToolId("");
    setInputMd("");
    setOutputMd("");
    setStatusBarMsg("");
    setDefault();
    setSourceMsg("");
    setDestinationMsg("");
  };

  useEffect(() => {
    // Clean up function to clear all the socket messages
    return () => {
      setDefault();
    };
  }, []);

  useEffect(() => {
    if (Object.keys(message)?.length === 0) {
      return;
    }

    const state = message?.state;
    const msgComp = message?.component;
    if (state === "INPUT_UPDATE") {
      setInputMd(message?.message);
      return;
    }

    if (state === "OUTPUT_UPDATE") {
      setOutputMd(message?.message);
      return;
    }

    if (state === "MESSAGE") {
      setStatusBarMsg(message?.message);
      return;
    }

    if (msgComp === "SOURCE" && state === "RUNNING") {
      setSourceMsg("");
      setDestinationMsg("");
      const newSteps = [...steps].map((step) => {
        step["progress"] = "";
        step["status"] = "";
        return step;
      });
      setSteps(newSteps);
    }

    if (msgComp === "SOURCE") {
      const srcMsg = message?.state + ": " + message?.message;
      setSourceMsg(srcMsg);
      return;
    }

    if (msgComp === "DESTINATION") {
      const destMsg = message?.state + ": " + message?.message;
      setDestinationMsg(destMsg);
      setActiveToolId("");
      return;
    }

    if (msgComp === "NEXT_STEP") {
      setStepLoader((prev) => !prev);
      return;
    }

    const stepsCopy = [...(steps || [])];
    const newSteps = stepsCopy.map((step) => {
      const stepObj = { ...step };
      if (stepObj?.id !== msgComp) {
        return stepObj;
      }

      setActiveToolId(msgComp);
      stepObj["progress"] = message?.state;
      stepObj["status"] = message?.message;
      return stepObj;
    });
    setSteps(newSteps);
  }, [message]);

  const actionsMenuItems = [
    {
      key: "clear-cache",
      label: "Clear Cache",
    },
    {
      key: "clear-history",
      label: "Clear Processed File History",
    },
    {
      key: "debug",
      label: "Debug Previous Workflow",
    },
  ];

  return (
    <div className="workflow-builder-layout">
      <PageTitle title={projectName} />

      {/* Header */}
      <div className="workflow-builder-header">
        <div className="workflow-title">
          <Button type="text" icon={<LeftOutlined />} size="small" />
          <Typography.Text>
            Workflow Builder - Create AI-powered data processing workflows
          </Typography.Text>
        </div>
        <Dropdown
          menu={{ items: actionsMenuItems }}
          placement="bottomRight"
          trigger={["click"]}
        >
          <Button type="primary" icon={<MoreOutlined />}>
            Actions
          </Button>
        </Dropdown>
      </div>

      {/* Progress Section */}
      <div className="workflow-progress-section">
        <div className="progress-header">
          <Typography.Text className="progress-label">
            Workflow Setup Progress
          </Typography.Text>
          <Typography.Text className="progress-count">
            0 of 4 steps completed
          </Typography.Text>
        </div>
        <Progress percent={0} strokeColor="#1890ff" />
      </div>

      {/* 2x2 Grid */}
      <div className="workflow-grid-container">
        <Row gutter={[24, 24]}>
          {/* Configure Source Connector */}
          <Col span={12}>
            <WorkflowCard
              number="1"
              title="Configure Source Connector"
              description="Select and configure your data input connector"
              type={sourceTypes.connectors[0]}
              endpointDetails={source}
              message={sourceMsg}
            />
          </Col>

          {/* Configure Output Destination */}
          <Col span={12}>
            <WorkflowCard
              number="2"
              title="Configure Output Destination"
              description="Select and configure your data output connector"
              type={sourceTypes.connectors[1]}
              endpointDetails={destination}
              message={destinationMsg}
            />
          </Col>

          {/* Select Prompt Studio Project */}
          <Col span={12}>
            <WorkflowCard
              number="3"
              title="Select Prompt Studio Project"
              description="Choose the AI tool for processing your data"
              customContent={
                <div className="workflow-card-content">
                  <Select
                    className="workflow-select"
                    placeholder="Select Project"
                    value={selectedProject}
                    onChange={setSelectedProject}
                    options={promptStudioProjects.map((project) => ({
                      value: project.id,
                      label: project.tool_name || project.name,
                    }))}
                  />
                  <Button
                    type="primary"
                    onClick={() => setShowSidebar(!showSidebar)}
                  >
                    Configure Settings
                  </Button>
                </div>
              }
            />
          </Col>

          {/* Deploy Workflow */}
          <Col span={12}>
            <WorkflowCard
              number="4"
              title="Deploy Workflow"
              description="Deploy your workflow for processing"
              customContent={
                <div className="workflow-card-content">
                  <Select
                    className="workflow-select"
                    placeholder="Select Deployment Type"
                    value={selectedDeploymentType}
                    onChange={handleDeploymentTypeChange}
                    options={[
                      { value: "API", label: "Deploy as API" },
                      { value: "ETL", label: "Deploy as ETL Pipeline" },
                      { value: "TASK", label: "Deploy as Task Pipeline" },
                    ]}
                  />
                  <Button
                    type="primary"
                    disabled={!selectedDeploymentType}
                    onClick={() =>
                      selectedDeploymentType &&
                      handleDeployBtnClick(selectedDeploymentType)
                    }
                  >
                    Deploy Workflow
                  </Button>
                </div>
              }
            />
          </Col>
        </Row>
      </div>

      {/* Debug Panel */}
      <div className="debug-panel">
        <div className="debug-panel-header">
          <div className="debug-panel-title">
            <BugOutlined />
            <Typography.Text>Debug Panel</Typography.Text>
          </div>
          <Button
            type="text"
            onClick={() => setShowDebug(!showDebug)}
            className="show-debug-btn"
          >
            Show Debug {showDebug ? "▲" : "▼"}
          </Button>
        </div>
        {showDebug && (
          <div className="debug-panel-content">
            <Typography.Text type="secondary">
              Select a workflow stage to see input and output data here.
            </Typography.Text>
          </div>
        )}
      </div>

      {/* Sidebar - conditionally shown */}
      {showSidebar && (
        <div className="workflow-sidebar">
          <SidePanel />
          <Button
            className="close-sidebar-btn"
            onClick={() => setShowSidebar(false)}
            size="small"
          >
            ×
          </Button>
        </div>
      )}

      {/* Actions - Hidden by default, can be shown via Actions dropdown */}
      <div style={{ display: "none" }}>
        <Actions
          statusBarMsg={statusBarMsg}
          initializeWfComp={initializeWfComp}
          stepLoader={stepLoader}
        />
      </div>

      {/* Deployment Modals */}
      <CreateApiDeploymentModal
        open={openAddApiModal}
        setOpen={setOpenAddApiModal}
        workflowId={details?.id}
      />

      <EtlTaskDeploy
        open={openAddETLModal}
        setOpen={setOpenAddETLModal}
        type="ETL"
        workflowId={details?.id}
      />

      <EtlTaskDeploy
        open={openAddTaskModal}
        setOpen={setOpenAddTaskModal}
        type="TASK"
        workflowId={details?.id}
      />
    </div>
  );
}

export { Agency };
