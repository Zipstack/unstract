import { Divider } from "antd";
import PropTypes from "prop-types";
import { useEffect } from "react";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";

import {
  handleException,
  sourceTypes,
} from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { DsSettingsCard } from "../ds-settings-card/DsSettingsCard.jsx";
import { StepCard } from "../step-card/StepCard.jsx";
import "./Steps.css";

function Steps({ steps, setSteps, activeToolId, sourceMsg, destinationMsg }) {
  const workflowStore = useWorkflowStore();
  const {
    projectId,
    details,
    isLoading,
    loadingType,
    addNewTool,
    source,
    destination,
    updateWorkflow,
  } = workflowStore;
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    getWfEndpointDetails();
    canUpdateWorkflow();
  }, []);

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

  const moveItem = (fromIndex, toIndex, funcName, dragging) => {
    if (fromIndex === undefined && funcName) {
      handleAddToolInstance(funcName)
        .then((res) => {
          const data = res?.data;
          const newList = [...steps];
          newList.push(data);
          addNewTool(data);
          return rearrangeTools(newList);
        })
        .then((res) => {
          setSteps(res);
        })
        .catch((err) => {
          const msg = "Failed to re-order the tools.";
          setAlertDetails(handleException(err, msg));
        });
    } else {
      const updatedSteps = [...steps];
      const [movedStep] = updatedSteps.splice(fromIndex, 1);
      updatedSteps.splice(toIndex, 0, movedStep);
      if (!dragging) {
        rearrangeTools(steps).then((res) => {
          setSteps(res);
        });
      } else {
        rearrangeTools(updatedSteps).then((res) => {
          setSteps(updatedSteps);
        });
      }
    }
  };

  const rearrangeTools = async (updatedSteps) => {
    // API to update the order
    const toolInstances = updatedSteps.map((step) => step?.id);
    const body = {
      workflow_id: details?.id,
      tool_instances: toolInstances,
    };
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_instance/reorder/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then(() => {
        details.tool_instances = updatedSteps;
        return updatedSteps;
      })

      .catch((err) => {
        throw err;
      });
  };

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

  const handleAddToolInstance = (funcName) => {
    const workflowId = details?.id;
    if (!workflowId || !funcName) {
      return;
    }

    const body = {
      tool_id: funcName,
      workflow_id: workflowId,
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

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  return (
    <div className="wf-steps-layout">
      <div className="ds-src-set">
        <DsSettingsCard
          type={sourceTypes.connectors[0]}
          endpointDetails={source}
          message={sourceMsg}
        />
        <Divider className="wf-steps-div" />
      </div>
      <div className="wf-steps-list">
        <div className="wf-steps-list-2">
          {isLoading && loadingType === "GENERATE" ? (
            <div className="wf-steps-layout">
              <SpinnerLoader />
            </div>
          ) : (
            <DndProvider backend={HTML5Backend}>
              <StepCard
                steps={steps}
                activeTool={activeToolId}
                moveItem={moveItem}
              />
            </DndProvider>
          )}
        </div>
      </div>
      <div className="ds-dst-set">
        <Divider className="wf-steps-div" />
        <DsSettingsCard
          type={sourceTypes.connectors[1]}
          endpointDetails={destination}
          message={destinationMsg}
        />
      </div>
    </div>
  );
}

Steps.propTypes = {
  steps: PropTypes.array,
  setSteps: PropTypes.func,
  activeToolId: PropTypes.string,
  sourceMsg: PropTypes.string,
  destinationMsg: PropTypes.string,
};

export { Steps };
