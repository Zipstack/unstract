import {
  Button,
  Col,
  Row,
  Select,
  Space,
  Tooltip,
  Typography,
  Image,
} from "antd";
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
  const [options, setOptions] = useState([]);
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
        setOptions([]);
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
    if (!destination) {
      return;
    }

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
    if (!endpointDetails?.id) {
      return;
    }

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
    if (!endpointDetails?.connection_type) {
      return "Select the connector type from the dropdown";
    }
    return "";
  };

  // Check if connector is configured
  const isConnectorConfigured = () => {
    // For API connections, connector_instance is not required
    if (endpointDetails?.connection_type === "API") {
      return true;
    }

    // For other connection types (Database, etc.), check if connector instance is configured
    // connector_instance represents the actual configured connector with credentials
    return !!endpointDetails?.connector_instance;
  };

  // Get configure button text based on configuration status
  const getConfigureButtonText = () => {
    if (!endpointDetails?.connection_type) {
      return "Configure";
    }

    return isConnectorConfigured() ? "Configured" : "Configure";
  };

  return (
    <>
      <Row className="ds-set-card-row">
        <Col span={12} className="ds-set-card-col2">
          <SpaceWrapper>
            {message && (
              <Typography.Paragraph
                ellipsis={{ rows: 2, expandable: false }}
                className="font-size-12 ds-set-card-message"
                type="secondary"
              >
                {message}
              </Typography.Paragraph>
            )}
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
                    connMode === "APPDEPLOYMENT"
                  }
                >
                  {getConfigureButtonText()}
                </Button>
              </Tooltip>
            </Space>
          </SpaceWrapper>
          {connDetails?.id && (
            <div className="ds-connector-info-wrapper">
              <Space className="ds-connector-info">
                {connDetails?.icon && (
                  <Image
                    src={connDetails.icon}
                    width={20}
                    height={20}
                    preview={false}
                    alt="connector-icon"
                  />
                )}
                <Typography.Text
                  className="ds-connector-name"
                  ellipsis={{ tooltip: true }}
                >
                  {connDetails?.connector_name || "Unnamed Connector"}
                </Typography.Text>
              </Space>
            </div>
          )}
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
