import {
  Button,
  Row,
  Col,
  Typography,
  Progress,
  Dropdown,
  Select,
  Alert,
} from "antd";
import { BugOutlined, SettingOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Actions } from "../actions/Actions";
import "./Agency.css";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
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
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
function Agency() {
  const [steps, setSteps] = useState([]);
  const [workflowProgress, setWorkflowProgress] = useState(0);
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
  const { orgName } = sessionDetails;
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
  const [exportedTools, setExportedTools] = useState([]);
  const [selectedTool, setSelectedTool] = useState(null);
  const [selectedDeploymentType, setSelectedDeploymentType] = useState(null);
  const [openAddApiModal, setOpenAddApiModal] = useState(false);
  const [openAddETLModal, setOpenAddETLModal] = useState(false);
  const [openAddTaskModal, setOpenAddTaskModal] = useState(false);
  const [deploymentName, setDeploymentName] = useState("");
  const [deploymentType, setDeploymentType] = useState("");
  const [apiOpsPresent, setApiOpsPresent] = useState(false);
  const [canAddTaskPipeline, setCanAddTaskPipeline] = useState(false);
  const [canAddETLPipeline, setCanAddETLPipeline] = useState(false);

  const { setPostHogCustomEvent } = usePostHogEvents();

  useEffect(() => {
    getWfEndpointDetails();
    canUpdateWorkflow();
    getExportedTools();
    initializeSelectedTool();
  }, []);

  useEffect(() => {
    if (apiOpsPresent) {
      setDeploymentType("API");
    } else if (canAddTaskPipeline) {
      setDeploymentType("Task Pipeline");
    } else if (canAddETLPipeline) {
      setDeploymentType("ETL Pipeline");
    }
  }, [deploymentName]);

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

  useEffect(() => {
    // Enable Deploy as API only when
    // Source & Destination connection_type are selected as API
    setApiOpsPresent(
      source?.connection_type === "API" &&
        destination?.connection_type === "API"
    );
    // Enable Deploy as Task Pipeline only when
    // destination connection_type is FILESYSTEM and Source & Destination are Configured
    setCanAddTaskPipeline(
      destination?.connection_type === "FILESYSTEM" &&
        source?.connector_instance &&
        destination?.connector_instance
    );
    // Enable Deploy as ETL Pipeline only when
    // destination connection_type is DATABASE and Source & Destination are Configured
    setCanAddETLPipeline(
      source?.connector_instance &&
        ((destination?.connection_type === "DATABASE" &&
          destination.connector_instance) ||
          destination.connection_type === "MANUALREVIEW")
    );
  }, [source, destination]);

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

  const getExportedTools = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/tool/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];
        setExportedTools(data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to get exported tools"));
      });
  };

  // Initialize selected tool from existing tool instances on page load
  const initializeSelectedTool = () => {
    if (details?.tool_instances?.length > 0) {
      const toolInstance = details.tool_instances[0]; // Get first tool instance
      setSelectedTool(toolInstance.tool_id);
    }
  };

  // Check if workflow has any active deployments (for progress calculation)
  const checkDeploymentStatus = async () => {
    try {
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${details?.id}/deployment/`,
      };
      const res = await axiosPrivate(requestOptions);
      const deployments = res?.data || [];

      // Check if any deployment is active
      const hasActiveDeployment = deployments.some(
        (deployment) => deployment.is_active === true
      );

      return hasActiveDeployment;
    } catch (err) {
      return false;
    }
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

  // Get deployment status text for a specific type
  const getDeploymentStatusText = (type) => {
    return `Deploy as ${type}`;
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

  // Get connector status information
  const getConnectorStatus = (endpoint) => {
    if (!endpoint?.connector_instance) {
      return { configured: false, type: null, name: null };
    }

    // For filesystem connectors, they are automatically configured
    if (endpoint.connection_type === "FILESYSTEM") {
      return {
        configured: true,
        type: "File System",
        name: "Local File System",
      };
    }

    return {
      configured: true,
      type: endpoint.connection_type,
      name: endpoint.connector_name || "Configured",
    };
  };

  // Calculate workflow progress based on completed steps
  const calculateProgress = async () => {
    let completedSteps = 0;

    // Check if source connector is configured
    const sourceStatus = getConnectorStatus(source);
    if (sourceStatus.configured) {
      completedSteps++;
    }

    // Check if destination connector is configured
    const destStatus = getConnectorStatus(destination);
    if (destStatus.configured) {
      completedSteps++;
    }

    // Check if tool is selected AND tool instance exists
    if (selectedTool && details?.tool_instances?.length > 0) {
      completedSteps++;
    }

    // Check if workflow has active deployments (step 4)
    const hasActiveDeployment = await checkDeploymentStatus();
    if (hasActiveDeployment) {
      completedSteps++;
    }

    const progress = (completedSteps / 4) * 100;
    return { progress, completedSteps };
  };

  // Initialize selected tool when workflow details are loaded
  useEffect(() => {
    if (details?.tool_instances?.length > 0 && !selectedTool) {
      initializeSelectedTool();
    }
  }, [details?.tool_instances, details?.id]);

  // Update progress whenever relevant state changes
  useEffect(() => {
    const updateProgress = async () => {
      const { progress } = await calculateProgress();
      setWorkflowProgress(progress);
    };
    updateProgress();
  }, [source, destination, selectedTool, details?.tool_instances]);

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
    <IslandLayout>
      <div className="workflow-builder-layout">
        <PageTitle title={projectName} />

        {/* Header */}
        <div className="workflow-builder-header">
          <div className="workflow-progress-section">
            <div className="progress-header">
              <Typography.Text className="progress-label">
                Workflow Setup Progress
              </Typography.Text>
              <Typography.Text className="progress-count">
                {Math.floor(workflowProgress / 25)} of 4 steps completed
              </Typography.Text>
            </div>
            <Progress percent={workflowProgress} strokeColor="#1890ff" />
          </div>
          <Dropdown
            menu={{ items: actionsMenuItems }}
            placement="bottomRight"
            trigger={["click"]}
          >
            <Button type="primary" icon={<SettingOutlined />}>
              Actions
            </Button>
          </Dropdown>
        </div>

        {/* Progress Section */}

        {/* 2x2 Grid */}
        <div className="workflow-grid-container">
          <Row gutter={[24, 24]}>
            {/* Configure Source Connector */}
            <Col span={12}>
              <WorkflowCard
                number={(() => {
                  const status = getConnectorStatus(source);
                  return status.configured ? "✓" : "1";
                })()}
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
                number={(() => {
                  const status = getConnectorStatus(destination);
                  return status.configured ? "✓" : "2";
                })()}
                title="Configure Output Destination"
                description="Select and configure your data output connector"
                type={sourceTypes.connectors[1]}
                endpointDetails={destination}
                message={destinationMsg}
              />
            </Col>
            <Col span={12}>
              <WorkflowCard
                number={selectedTool ? "✓" : "3"}
                title="Select Exported Tool"
                description="Choose an exported tool for processing your data"
                customContent={
                  <div className="workflow-card-content">
                    <Select
                      className="workflow-select"
                      placeholder="Select Tool"
                      value={selectedTool}
                      onChange={async (functionName) => {
                        setSelectedTool(functionName);

                        const tool = exportedTools.find(
                          (t) => t.function_name === functionName
                        );

                        if (tool && details?.id) {
                          try {
                            // Check if there are existing tool instances
                            if (details?.tool_instances?.length > 0) {
                              // Remove existing tool instances
                              for (const existingTool of details.tool_instances) {
                                const deleteOptions = {
                                  method: "DELETE",
                                  url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_instance/${existingTool.id}/`,
                                  headers: {
                                    "X-CSRFToken": sessionDetails?.csrfToken,
                                  },
                                };
                                await axiosPrivate(deleteOptions);
                              }

                              // Update workflow store to remove old tool instances
                              const { deleteToolInstance } =
                                useWorkflowStore.getState();
                              details.tool_instances.forEach((instance) => {
                                deleteToolInstance(instance.id);
                              });
                            }

                            // Create new tool instance
                            const body = {
                              tool_id: functionName,
                              workflow_id: details.id,
                            };

                            const requestOptions = {
                              method: "POST",
                              url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_instance/`,
                              headers: {
                                "X-CSRFToken": sessionDetails?.csrfToken,
                                "Content-Type": "application/json",
                              },
                              data: body,
                            };

                            const res = await axiosPrivate(requestOptions);
                            const newToolInstance = res.data;

                            // Update tool settings for sidebar
                            const { setToolSettings } =
                              useToolSettingsStore.getState();
                            setToolSettings({
                              id: newToolInstance.id,
                              tool_id: newToolInstance.tool_id,
                            });

                            // Update workflow store with new tool instance
                            const { addNewTool } = useWorkflowStore.getState();
                            addNewTool(newToolInstance);

                            setAlertDetails({
                              type: "success",
                              content:
                                details?.tool_instances?.length > 0
                                  ? "Tool replaced successfully"
                                  : "Tool added successfully",
                            });
                          } catch (err) {
                            setAlertDetails(
                              handleException(err, "Failed to update tool")
                            );
                          }
                        }
                      }}
                      options={exportedTools.map((tool) => {
                        return {
                          value: tool.function_name,
                          label: tool.name,
                        };
                      })}
                    />
                    <Button
                      type="primary"
                      onClick={() => setShowSidebar(!showSidebar)}
                      disabled={!selectedTool}
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
                number={details?.tool_instances?.length > 0 ? "✓" : "4"}
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
                        {
                          value: "API",
                          label: getDeploymentStatusText("API"),
                          disabled: false,
                        },
                        {
                          value: "ETL",
                          label: getDeploymentStatusText("ETL"),
                          disabled: false,
                        },
                        {
                          value: "TASK",
                          label: getDeploymentStatusText("TASK"),
                          disabled: false,
                        },
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
        {deploymentName && (
          <Alert
            message={
              <>
                <span>
                  This Workflow has been deployed as an {deploymentType}:{" "}
                </span>
                <Link
                  to={`/${orgName}/${deploymentType
                    .split(" ")[0]
                    .toLowerCase()}`}
                >
                  {deploymentName}
                </Link>
              </>
            }
            type="success"
          />
        )}

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
        {openAddApiModal && (
          <CreateApiDeploymentModal
            open={openAddApiModal}
            setOpen={setOpenAddApiModal}
            workflowId={details?.id}
            isEdit={false}
            setDeploymentName={setDeploymentName}
          />
        )}

        <EtlTaskDeploy
          open={openAddETLModal}
          setOpen={setOpenAddETLModal}
          type="ETL"
          workflowId={details?.id}
          setDeploymentName={setDeploymentName}
        />

        <EtlTaskDeploy
          open={openAddTaskModal}
          setOpen={setOpenAddTaskModal}
          type="TASK"
          workflowId={details?.id}
          setDeploymentName={setDeploymentName}
        />
      </div>
    </IslandLayout>
  );
}

export { Agency };
