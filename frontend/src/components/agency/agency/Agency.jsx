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
import {
  BugOutlined,
  SettingOutlined,
  PlayCircleOutlined,
  ClearOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import "./Agency.css";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { SidePanel } from "../side-panel/SidePanel";
import { PageTitle } from "../../widgets/page-title/PageTitle";
import { WorkflowCard } from "../workflow-card/WorkflowCard";
import { sourceTypes, wfExecutionTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import useRequestUrl from "../../../hooks/useRequestUrl";
import { CreateApiDeploymentModal } from "../../deployments/create-api-deployment-modal/CreateApiDeploymentModal.jsx";
import { EtlTaskDeploy } from "../../pipelines-or-deployments/etl-task-deploy/EtlTaskDeploy.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import FileUpload from "../file-upload/FileUpload.jsx";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { apiDeploymentsService } from "../../deployments/api-deployment/api-deployments-service.js";
import { pipelineService } from "../../pipelines-or-deployments/pipeline-service.js";
import { InputOutput } from "../input-output/InputOutput";
import { ToolSelectionSidebar } from "../tool-selection-sidebar/ToolSelectionSidebar.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
function Agency() {
  const [steps, setSteps] = useState([]);
  const [workflowProgress, setWorkflowProgress] = useState(0);
  const [inputMd, setInputMd] = useState("");
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
    allowChangeEndpoint,
  } = workflowStore;
  const { sessionDetails } = useSessionStore();
  const { orgName } = sessionDetails;
  const { getUrl } = useRequestUrl();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const apiDeploymentService = apiDeploymentsService();
  const pipelineServiceInstance = pipelineService();
  const prompt = details?.prompt_text;
  const [prevLoadingType, setPrevLoadingType] = useState("");
  const [isUpdateSteps, setIsUpdateSteps] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [showToolSelectionSidebar, setShowToolSelectionSidebar] =
    useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
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
  const [deploymentInfo, setDeploymentInfo] = useState(null);
  const [executionId, setExecutionId] = useState("");
  const [openFileUploadModal, setOpenFileUploadModal] = useState(false);
  const [fileList, setFileList] = useState([]);
  const [wfExecutionParams, setWfExecutionParams] = useState([]);

  const { setPostHogCustomEvent } = usePostHogEvents();

  useEffect(() => {
    const abortController = new AbortController();
    const signal = abortController.signal;

    const initializeData = async () => {
      try {
        setIsInitialLoading(true);
        await Promise.all([
          getWfEndpointDetails(signal),
          canUpdateWorkflow(signal),
          getExportedTools(signal),
        ]);

        if (!signal.aborted) {
          initializeSelectedTool();
        }
      } catch (error) {
        if (!signal.aborted) {
          console.error("Error initializing workflow data:", error);
        }
      } finally {
        if (!signal.aborted) {
          // Add a small delay to prevent flash of content
          setTimeout(() => {
            setIsInitialLoading(false);
          }, 500);
        }
      }
    };

    initializeData();

    return () => {
      abortController.abort();
    };
  }, []);

  useEffect(() => {
    if (apiOpsPresent) {
      setDeploymentType("API");
    } else if (canAddTaskPipeline) {
      setDeploymentType("Task Pipeline");
    } else if (canAddETLPipeline) {
      setDeploymentType("ETL Pipeline");
    }
  }, [apiOpsPresent, canAddTaskPipeline, canAddETLPipeline]);

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
    const isApiOps =
      source?.connection_type === "API" &&
      destination?.connection_type === "API";
    setApiOpsPresent(isApiOps);

    // Clear deployment selection when connector types change
    // This ensures user has to re-select deployment type after changing connectors
    setSelectedDeploymentType(null);
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

  const getWfEndpointDetails = (signal) => {
    const requestOptions = {
      method: "GET",
      url: getUrl(`workflow/${projectId}/endpoint/`),
      signal,
    };
    return axiosPrivate(requestOptions)
      .then((res) => {
        if (!signal?.aborted) {
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
        }
      })
      .catch((err) => {
        if (!signal?.aborted) {
          setAlertDetails(handleException(err, "Failed to get endpoints"));
        }
        throw err;
      });
  };

  const canUpdateWorkflow = (signal) => {
    const requestOptions = {
      method: "GET",
      url: getUrl(`workflow/${projectId}/can-update/`),
      signal,
    };
    return axiosPrivate(requestOptions)
      .then((res) => {
        if (!signal?.aborted) {
          const data = res?.data || {};
          const body = {
            allowChangeEndpoint: data?.can_update,
          };
          updateWorkflow(body);
        }
      })
      .catch((err) => {
        if (!signal?.aborted) {
          setAlertDetails(
            handleException(err, "Failed to get can update status")
          );
        }
        throw err;
      });
  };

  const getExportedTools = (signal) => {
    const requestOptions = {
      method: "GET",
      url: getUrl(`tool/`),
      signal,
    };
    return axiosPrivate(requestOptions)
      .then((res) => {
        if (!signal?.aborted) {
          const data = res?.data || [];
          setExportedTools(data);
        }
      })
      .catch((err) => {
        if (!signal?.aborted) {
          setAlertDetails(handleException(err, "Failed to get exported tools"));
        }
        throw err;
      });
  };

  // Fetch deployment information for the current workflow
  const fetchDeploymentInfo = async (signal) => {
    if (!projectId) {
      return;
    }

    try {
      // Fetch API deployments and pipelines in parallel
      const [apiDeployments, pipelines] = await Promise.all([
        apiDeploymentService.getDeploymentsByWorkflowId(projectId),
        pipelineServiceInstance.getPipelinesByWorkflowId(projectId),
      ]);

      // Check if request was aborted before setting state
      if (signal?.aborted) {
        return;
      }

      const apiDeploymentData = apiDeployments?.data || [];
      const pipelineData = pipelines?.data || [];

      // Find active deployments
      const activeApiDeployment = apiDeploymentData.find(
        (deployment) => deployment.is_active
      );

      // For pipelines, any pipeline associated with this workflow is considered a deployment
      // regardless of active status, since workflows can only have one deployment
      const workflowPipelines = pipelineData;

      // Set deployment info
      let deploymentInfo = null;
      if (activeApiDeployment) {
        deploymentInfo = {
          type: "API",
          name: activeApiDeployment.display_name,
          id: activeApiDeployment.id,
        };
      } else if (workflowPipelines.length > 0) {
        // If multiple pipelines, prioritize by type: ETL > TASK
        const etlPipeline = workflowPipelines.find(
          (p) => p.pipeline_type === "ETL"
        );
        const taskPipeline = workflowPipelines.find(
          (p) => p.pipeline_type === "TASK"
        );
        const pipeline = etlPipeline || taskPipeline || workflowPipelines[0];

        deploymentInfo = {
          type: pipeline.pipeline_type,
          name: pipeline.pipeline_name,
          id: pipeline.id,
        };
      }

      if (!signal?.aborted) {
        setDeploymentInfo(deploymentInfo);
      }
    } catch (err) {
      // Don't show alert for this as it's not critical
      // Also check if error is due to abort
      if (signal?.aborted) {
        return;
      }
    }
  };

  // Initialize selected tool from existing tool instances on page load
  const initializeSelectedTool = () => {
    if (details?.tool_instances?.length > 0) {
      const toolInstance = details.tool_instances[0]; // Get first tool instance
      setSelectedTool(toolInstance.tool_id);

      // Also update tool settings store for proper sidebar functionality
      const { setToolSettings } = useToolSettingsStore.getState();
      setToolSettings({
        id: toolInstance.id,
        tool_id: toolInstance.tool_id,
      });
    }
  };

  // Check if workflow has any active deployments (for progress calculation)
  // Check if workflow is deployed using allowChangeEndpoint flag
  const isWorkflowDeployed = () => {
    // When allowChangeEndpoint is false, workflow is deployed and locked
    return !allowChangeEndpoint;
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
  };

  // Get deployment status text for a specific type
  const getDeploymentStatusText = (type) => {
    return `Deploy as ${type}`;
  };

  // Get available deployment options based on source and destination types
  const getDeploymentOptions = () => {
    // If both source and destination are API, only show API option
    if (
      source?.connection_type === "API" &&
      destination?.connection_type === "API"
    ) {
      return [
        {
          value: "API",
          label: getDeploymentStatusText("API"),
          disabled: false,
        },
      ];
    }

    // If source is FILESYSTEM, determine options based on destination
    if (source?.connection_type === "FILESYSTEM") {
      const options = [];

      // If destination is Database or ManualReview → show ETL only
      if (
        destination?.connection_type === "DATABASE" ||
        destination?.connection_type === "MANUALREVIEW"
      ) {
        options.push({
          value: "ETL",
          label: getDeploymentStatusText("ETL"),
          disabled: false,
        });
      }
      // If destination is FileSystem → show TASK only
      else if (destination?.connection_type === "FILESYSTEM") {
        options.push({
          value: "TASK",
          label: getDeploymentStatusText("TASK"),
          disabled: false,
        });
      }
      // If destination is API → show API only
      else if (destination?.connection_type === "API") {
        options.push({
          value: "API",
          label: getDeploymentStatusText("API"),
          disabled: false,
        });
      }

      return options;
    }

    // Default case - return empty array if no valid combination
    return [];
  };

  // Generate deployment alert message content
  const generateDeploymentMessage = () => {
    if (deploymentInfo) {
      const article = deploymentInfo.type === "API" ? "an" : "a";
      const urlPath =
        deploymentInfo.type === "API"
          ? "api"
          : deploymentInfo.type.toLowerCase();

      return (
        <>
          {article} {deploymentInfo.type}:{" "}
          <Link to={`/${orgName}/${urlPath}`}>{deploymentInfo.name}</Link>
        </>
      );
    } else {
      const urlPath = deploymentType.split(" ")[0].toLowerCase();

      return (
        <>
          an {deploymentType}:{" "}
          <Link to={`/${orgName}/${urlPath}`}>{deploymentName}</Link>
        </>
      );
    }
  };

  const setToolInstances = () => {
    const toolInstances = [...(details?.tool_instances || [])];
    setSteps(toolInstances);
  };

  const initializeWfComp = () => {
    setToolInstances();
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
      return;
    }

    if (msgComp === "NEXT_STEP") {
      // Step execution is disabled - ignoring NEXT_STEP messages
      return;
    }

    const stepsCopy = [...(steps || [])];
    const newSteps = stepsCopy.map((step) => {
      const stepObj = { ...step };
      if (stepObj?.id !== msgComp) {
        return stepObj;
      }

      stepObj["progress"] = message?.state;
      stepObj["status"] = message?.message;
      return stepObj;
    });
    setSteps(newSteps);
  }, [message]);

  // Get connector status information
  const getConnectorStatus = (endpoint, isDeployed = false) => {
    // If workflow is deployed, connectors are considered completed
    if (isDeployed) {
      return {
        configured: true,
        type: endpoint?.connection_type || "Deployed",
        name: endpoint?.connector_name || "Configured",
      };
    }

    // If no endpoint exists, not configured
    if (!endpoint) {
      return { configured: false, type: null, name: null };
    }

    // For API connections, just having an endpoint is sufficient
    if (endpoint.connection_type === "API") {
      return {
        configured: true,
        type: "API",
        name: endpoint.connector_name || "API Endpoint",
      };
    }

    // For filesystem connectors, they are automatically configured
    if (endpoint.connection_type === "FILESYSTEM") {
      return {
        configured: true,
        type: "File System",
        name: "Local File System",
      };
    }

    // For other connection types, check if connector instance is configured
    if (!endpoint?.connector_instance) {
      return { configured: false, type: null, name: null };
    }

    return {
      configured: true,
      type: endpoint.connection_type,
      name: endpoint.connector_name || "Configured",
    };
  };

  // Calculate workflow progress based on completed steps
  const calculateProgress = () => {
    let completedSteps = 0;

    // Check if source connector is configured
    const sourceStatus = getConnectorStatus(source, !allowChangeEndpoint);
    if (sourceStatus.configured) {
      completedSteps++;
    }

    // Check if destination connector is configured
    const destStatus = getConnectorStatus(destination, !allowChangeEndpoint);
    if (destStatus.configured) {
      completedSteps++;
    }

    // Check if tool is selected AND tool instance exists
    if (selectedTool && details?.tool_instances?.length > 0) {
      completedSteps++;
    }

    // Check if workflow is deployed (step 4)
    const workflowDeployed = isWorkflowDeployed() || deploymentInfo !== null;
    if (workflowDeployed) {
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

  // Refresh deployment info when allowChangeEndpoint changes (indicates deployment status change)
  useEffect(() => {
    if (projectId) {
      const abortController = new AbortController();
      fetchDeploymentInfo(abortController.signal);

      return () => {
        abortController.abort();
      };
    }
  }, [allowChangeEndpoint, projectId]);

  // Update progress whenever relevant state changes
  useEffect(() => {
    const { progress } = calculateProgress();
    setWorkflowProgress(progress);
  }, [
    source,
    destination,
    selectedTool,
    details?.tool_instances,
    allowChangeEndpoint,
    deploymentInfo,
  ]);

  // Disable Run & Step execution - when NO tool present in the workflow
  // When source OR destination is NOT configured
  const disableAction = () => {
    if (!details?.tool_instances?.length) {
      return true;
    }
    if (
      source?.connection_type === "API" &&
      destination?.connection_type === "API"
    ) {
      return false;
    }
    if (
      source?.connection_type === "FILESYSTEM" &&
      destination?.connection_type === "MANUALREVIEW"
    ) {
      return false;
    }
    return !source?.connector_instance || !destination?.connector_instance;
  };

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
      body["execution_action"] = wfExecutionTypes[0];
    }

    const loadingStatus = {
      isLoading: true,
      loadingType: "EXECUTE",
    };
    updateWorkflow(loadingStatus);

    try {
      const initialRes = await handleWfExecutionApi(body);
      const execIdValue = initialRes?.data?.execution_id;

      setExecutionId(execIdValue);
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

  const handleClearStates = () => {
    setExecutionId("");
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
      url: getUrl(`workflow/execute/`),
      headers: header,
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const handleWfExecution = async (
    isInitial,
    isStepExecution,
    executionAction
  ) => {
    try {
      if (isStepExecution) {
        setPostHogCustomEvent("wf_step", {
          info: `Clicked on '${wfExecutionTypes[executionAction]}' button (Step Execution)`,
        });
      } else {
        setPostHogCustomEvent("wf_run_wf", {
          info: "Clicked on 'Run Workflow' button (Normal Execution)",
        });
      }
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
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
      body["execution_id"] = executionId;
      body["execution_action"] = wfExecutionTypes[executionAction];

      handleWfExecutionApi(body)
        .then(() => {})
        .catch((err) => {
          setAlertDetails(handleException(err));
        });
    }
  };

  // Handle Run Workflow action
  const handleRunWorkflow = async () => {
    if (disableAction()) {
      setAlertDetails({
        type: "error",
        content: "Please configure all workflow components before running",
      });
      return;
    }

    // Auto-open debug panel when workflow starts
    setShowDebug(true);

    if (apiOpsPresent) {
      getInputFile(true, false, 4);
    } else {
      await handleWfExecution(true, false, 4);
    }
  };

  // Handle Clear Cache action
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
      url: getUrl(`workflow/${workflowId}/clear-cache/`),
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

  // Handle tool selection from sidebar
  const handleToolSelection = async (functionName) => {
    setSelectedTool(functionName);

    const tool = exportedTools.find((t) => t.function_name === functionName);

    if (tool && details?.id) {
      try {
        // Check if there are existing tool instances
        if (details?.tool_instances?.length > 0) {
          // Remove existing tool instances
          for (const existingTool of details.tool_instances) {
            const deleteOptions = {
              method: "DELETE",
              url: getUrl(`tool_instance/${existingTool.id}/`),
              headers: {
                "X-CSRFToken": sessionDetails?.csrfToken,
              },
            };
            await axiosPrivate(deleteOptions);
          }

          // Update workflow store to remove old tool instances
          const { deleteToolInstance } = useWorkflowStore.getState();
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
          url: getUrl(`tool_instance/`),
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: body,
        };

        const res = await axiosPrivate(requestOptions);
        const newToolInstance = res.data;

        // Update tool settings for sidebar
        const { setToolSettings } = useToolSettingsStore.getState();
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
        setAlertDetails(handleException(err, "Failed to update tool"));
      }
    }
  };

  // Handle Clear Processed File History action
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
      url: getUrl(`workflow/${workflowId}/clear-file-marker/`),
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

  // Handle dropdown menu click
  const handleMenuClick = ({ key }) => {
    switch (key) {
      case "run-workflow":
        handleRunWorkflow();
        break;
      case "clear-cache":
        handleClearCache();
        break;
      case "clear-history":
        handleClearFileMarker();
        break;
      default:
        break;
    }
  };

  const actionsMenuItems = [
    {
      key: "run-workflow",
      label: "Run Workflow",
      icon: <PlayCircleOutlined />,
    },
    {
      key: "clear-cache",
      label: "Clear Cache",
      icon: <ClearOutlined />,
    },
    {
      key: "clear-history",
      label: "Clear Processed File History",
      icon: <HistoryOutlined />,
    },
  ];

  // Show loading spinner during initial data load
  if (isInitialLoading) {
    return (
      <IslandLayout>
        <div className="agency-loading-container">
          <SpinnerLoader text="Loading workflow data..." align="center" />
        </div>
      </IslandLayout>
    );
  }

  return (
    <IslandLayout>
      <div className="agency-layout">
        <PageTitle title={projectName} />

        {/* Header */}
        <div className="agency-header">
          <div className="workflow-progress-section">
            <div className="progress-header">
              <Typography.Text className="progress-label">
                Workflow Setup Progress
              </Typography.Text>
              <Typography.Text className="progress-count">
                {Math.floor(workflowProgress / 25)} of 4 steps completed
              </Typography.Text>
            </div>
            <Progress
              percent={workflowProgress}
              strokeColor={workflowProgress === 100 ? "#52c41a" : "#1890ff"}
            />
          </div>
          <Dropdown
            menu={{ items: actionsMenuItems, onClick: handleMenuClick }}
            placement="bottomRight"
            trigger={["click"]}
          >
            <Button
              type="primary"
              icon={<SettingOutlined />}
              loading={loadingType === "EXECUTE"}
              disabled={loadingType === "EXECUTE"}
            >
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
                  const status = getConnectorStatus(
                    source,
                    !allowChangeEndpoint
                  );
                  // Show connector type for non-API configured connectors
                  if (
                    status?.configured &&
                    source?.connection_type &&
                    source?.connection_type !== "API"
                  ) {
                    return source?.connection_type;
                  }
                  return status?.configured ? "✓" : "1";
                })()}
                title="Configure Source Connector"
                description="Select and configure your data input connector"
                connType={sourceTypes.connectors[0]}
                endpointDetails={source}
                message={sourceMsg}
                connectorIcon={source?.connector_instance?.icon}
              />
            </Col>

            {/* Configure Output Destination */}
            <Col span={12}>
              <WorkflowCard
                number={(() => {
                  const status = getConnectorStatus(
                    destination,
                    !allowChangeEndpoint
                  );
                  // Show connector type for non-API configured connectors
                  if (
                    status?.configured &&
                    destination?.connection_type &&
                    destination?.connection_type !== "API"
                  ) {
                    return destination?.connection_type;
                  }
                  return status?.configured ? "✓" : "2";
                })()}
                title="Configure Destination Connector"
                description="Select and configure your data output connector"
                connType={sourceTypes.connectors[1]}
                endpointDetails={destination}
                message={destinationMsg}
                connectorIcon={destination?.connector_instance?.icon}
              />
            </Col>
            <Col span={12}>
              <WorkflowCard
                number={selectedTool ? "✓" : "3"}
                title="Select Exported Tool"
                description="Choose an exported tool for processing your data"
                customContent={
                  <div className="workflow-card-content">
                    <div className="tool-selection-display">
                      {selectedTool ? (
                        <div className="selected-tool-info">
                          <span className="selected-tool-name">
                            {exportedTools.find(
                              (t) => t.function_name === selectedTool
                            )?.name || selectedTool}
                          </span>
                          <Button
                            type="link"
                            onClick={() => setShowToolSelectionSidebar(true)}
                            size="small"
                          >
                            Change Tool
                          </Button>
                        </div>
                      ) : (
                        <Button
                          type="default"
                          onClick={() => setShowToolSelectionSidebar(true)}
                          className="select-tool-btn"
                        >
                          Select Tool
                        </Button>
                      )}
                    </div>
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
                number={deploymentInfo || !allowChangeEndpoint ? "✓" : "4"}
                title="Deploy Workflow"
                description="Deploy your workflow for processing"
                customContent={
                  <div className="workflow-card-content">
                    <Select
                      className="workflow-select"
                      placeholder={
                        !source?.connection_type ||
                        !destination?.connection_type
                          ? "Select both connectors first"
                          : "Select Deployment Type"
                      }
                      value={
                        deploymentInfo
                          ? deploymentInfo.type
                          : selectedDeploymentType
                      }
                      onChange={handleDeploymentTypeChange}
                      disabled={
                        deploymentInfo ||
                        !allowChangeEndpoint ||
                        !source?.connection_type ||
                        !destination?.connection_type
                      }
                      options={getDeploymentOptions()}
                    />
                    <Button
                      type="primary"
                      disabled={
                        deploymentInfo ||
                        !allowChangeEndpoint ||
                        !selectedDeploymentType ||
                        !source?.connection_type ||
                        !destination?.connection_type
                      }
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
        {(deploymentName || deploymentInfo) && (
          <Alert
            className="deployment-alert"
            message={
              <span>
                This Workflow has been deployed as {generateDeploymentMessage()}
              </span>
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
              {statusBarMsg && (
                <div className="status-message">
                  <Typography.Text type="secondary" className="status-text">
                    {statusBarMsg}
                  </Typography.Text>
                </div>
              )}
              <InputOutput input={inputMd} output={outputMd} />
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

        {/* File Upload Modal */}
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

        {/* Deployment Modals */}
        {openAddApiModal && (
          <CreateApiDeploymentModal
            open={openAddApiModal}
            setOpen={setOpenAddApiModal}
            workflowId={details?.id}
            isEdit={false}
            setDeploymentName={setDeploymentName}
            onDeploymentCreated={fetchDeploymentInfo}
          />
        )}

        <EtlTaskDeploy
          open={openAddETLModal}
          setOpen={setOpenAddETLModal}
          type="ETL"
          workflowId={details?.id}
          setDeploymentName={setDeploymentName}
          onDeploymentCreated={fetchDeploymentInfo}
          title="Deploy ETL"
        />

        <EtlTaskDeploy
          open={openAddTaskModal}
          setOpen={setOpenAddTaskModal}
          type="TASK"
          workflowId={details?.id}
          setDeploymentName={setDeploymentName}
          onDeploymentCreated={fetchDeploymentInfo}
          title="Deploy Task"
        />

        {/* Tool Selection Sidebar */}
        <ToolSelectionSidebar
          visible={showToolSelectionSidebar}
          onClose={() => setShowToolSelectionSidebar(false)}
          tools={exportedTools}
          selectedTool={selectedTool}
          onToolSelect={handleToolSelection}
          onSave={() => setShowToolSelectionSidebar(false)}
        />
      </div>
    </IslandLayout>
  );
}

export { Agency };
