import { Button, Col, Row, Select, Space, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import useRequestUrl from "../../../hooks/useRequestUrl";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { ConfigureConnectorModal } from "../configure-connector-modal/ConfigureConnectorModal";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DsSettingsCard.css";

function DsSettingsCard({ connType, endpointDetails, message }) {
  const workflowStore = useWorkflowStore();
  const { source, destination, allowChangeEndpoint, details } = workflowStore;
  const [options, setOptions] = useState({});
  const [openModal, setOpenModal] = useState(false);

  const [connMode, setConnMode] = useState(null);

  const [connDetails, setConnDetails] = useState({});
  const [formDataConfig, setFormDataConfig] = useState({});

  const [inputOptions, setInputOptions] = useState([
    {
      value: "API",
      label: "API",
    },
    {
      value: "FILESYSTEM",
      label: "File System",
    },
    {
      value: "DATABASE",
      label: "Database",
    },
  ]);

  const { sessionDetails } = useSessionStore();
  const { updateWorkflow } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { flags } = sessionDetails;
  const { getUrl } = useRequestUrl();

  const setUpdatedInputoptions = (inputOption) => {
    setInputOptions((prevInputOptions) => {
      // Check if inputOption already exists in prevInputOptions
      // Return previous state unchanged if it does or create new array
      if (prevInputOptions.some((opt) => opt.value === inputOption.value)) {
        return prevInputOptions;
      } else {
        const updatedInputOptions = [...prevInputOptions, inputOption];
        return updatedInputOptions;
      }
    });
  };

  useEffect(() => {
    try {
      const inputOption =
        require("../../../plugins/dscard-input-options/AppDeploymentCardInputOptions").appDeploymentInputOption;
      if (flags.app_deployment && inputOption) {
        setUpdatedInputoptions(inputOption);
      }
    } catch {
      // The component will remain null of it is not available
    }
  }, []);

  useEffect(() => {
    if (connType === "output") {
      if (source?.connection_type === "") {
        // Clear options when source is blank
        setOptions({});
      } else {
        // Filter options based on source connection type
        const isAPI = source?.connection_type === "API";
        const filteredOptions = inputOptions.filter((option) =>
          isAPI ? option.value === "API" : option.value !== "API"
        );

        setOptions(filteredOptions);
      }
    }

    if (connType === "input") {
      // Remove Database from Source Dropdown
      const filteredOptions = inputOptions.filter(
        (option) =>
          option.value !== "DATABASE" && option.value !== "APPDEPLOYMENT"
      );
      setOptions(filteredOptions);
    }
  }, [source, destination]);

  // Set formDataConfig from endpointDetails configuration
  useEffect(() => {
    if (endpointDetails?.configuration) {
      setFormDataConfig(endpointDetails.configuration);
    }
  }, [endpointDetails?.configuration]);

  useEffect(() => {
    if (endpointDetails?.connection_type !== connMode) {
      setConnMode(endpointDetails?.connection_type);
    }

    if (!endpointDetails?.connector_instance) {
      setConnDetails({});
      return;
    }

    // Use connector_instance data directly from endpointDetails if it's an object
    if (typeof endpointDetails?.connector_instance === "object") {
      setConnDetails(endpointDetails.connector_instance);
      return;
    }
  }, [endpointDetails]);

  const clearDestination = (updatedData) => {
    const requestOptions = {
      method: "PATCH",
      url: getUrl(`workflow/endpoint/${destination?.id}/`),
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: updatedData,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        const updatedData = {};
        updatedData["destination"] = data;
        updateWorkflow(updatedData);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      });
  };

  const updateDestination = () => {
    // Clear destination dropdown & data when input is switched
    if (connType === "input") {
      clearDestination({
        connection_type: "",
        connector_instance_id: null,
      });
    }
  };

  const handleEndpointUpdate = (updatedData, showSuccess) => {
    const requestOptions = {
      method: "PATCH",
      url: getUrl(`workflow/endpoint/${endpointDetails?.id}/`),
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: updatedData,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        const updatedData = {};
        if (connType === "input") {
          updatedData["source"] = data;
        } else {
          updatedData["destination"] = data;
        }
        updateWorkflow(updatedData);
        if (showSuccess) {
          setAlertDetails({
            type: "success",
            content: "Successfully updated",
          });
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      });
  };

  // Generate configure button tooltip message
  const getConfigureTooltipMessage = () => {
    if (!allowChangeEndpoint) {
      return "Configuration disabled - Workflow is deployed";
    }
    if (!endpointDetails?.connection_type) {
      return "Select the connector type from the dropdown";
    }
    return "";
  };

  return (
    <>
      <Row className="ds-set-card-row">
        <Col span={12} className="ds-set-card-col2">
          <SpaceWrapper>
            <Space>
              <Tooltip
                title={
                  !allowChangeEndpoint &&
                  "Workflow used in API/Task/ETL deployment"
                }
              >
                <Select
                  className="ds-set-card-select"
                  options={options}
                  placeholder="Select Connector Type"
                  value={endpointDetails?.connection_type || undefined}
                  disabled={!allowChangeEndpoint}
                  onChange={(value) => {
                    handleEndpointUpdate({
                      connection_type: value,
                      connector_instance_id: null,
                    });
                    updateDestination();
                  }}
                />
              </Tooltip>

              <Tooltip title={getConfigureTooltipMessage()}>
                <Button
                  type="primary"
                  onClick={() => setOpenModal(true)}
                  disabled={
                    !endpointDetails?.connection_type ||
                    connMode === "API" ||
                    connMode === "APPDEPLOYMENT" ||
                    !allowChangeEndpoint
                  }
                >
                  Configure
                </Button>
              </Tooltip>
            </Space>
          </SpaceWrapper>
        </Col>
        <Col span={8} className="ds-set-card-col3">
          <Typography.Paragraph
            ellipsis={{ rows: 2, expandable: false }}
            className="font-size-12"
            type="secondary"
          >
            {message}
          </Typography.Paragraph>
        </Col>
      </Row>
      <ConfigureConnectorModal
        open={openModal}
        setOpen={setOpenModal}
        connType={connType}
        handleEndpointUpdate={handleEndpointUpdate}
        endpointDetails={endpointDetails}
        formDataConfig={formDataConfig}
        setFormDataConfig={setFormDataConfig}
        connDetails={connDetails}
        setConnDetails={setConnDetails}
        connMode={connMode}
        workflowDetails={details}
      />
    </>
  );
}

DsSettingsCard.propTypes = {
  connType: PropTypes.string.isRequired,
  endpointDetails: PropTypes.object.isRequired,
  message: PropTypes.string,
};

export { DsSettingsCard };
