import {
  Button,
  Col,
  Image,
  Row,
  Select,
  Space,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { getMenuItem } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import useRequestUrl from "../../../hooks/useRequestUrl";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { ConfigureConnectorModal } from "../configure-connector-modal/ConfigureConnectorModal";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DsSettingsCard.css";

const disabledIdsByType = {
  FILE_SYSTEM: [
    "box|4d94d237-ce4b-45d8-8f34-ddeefc37c0bf",
    "http|6fdea346-86e4-4383-9a21-132db7c9a576",
  ],
};

const needToRemove = {
  FILE_SYSTEM: ["pcs|b8cd25cd-4452-4d54-bd5e-e7d71459b702"],
};

function DsSettingsCard({ type, endpointDetails, message }) {
  const workflowStore = useWorkflowStore();
  const { source, destination, allowChangeEndpoint, details } = workflowStore;
  const [options, setOptions] = useState({});
  const [openModal, setOpenModal] = useState(false);

  const [listOfConnectors, setListOfConnectors] = useState([]);
  const [filteredList, setFilteredList] = useState([]);

  const [connType, setConnType] = useState(null);

  const [connDetails, setConnDetails] = useState({});
  const [specConfig, setSpecConfig] = useState({});
  const [isSpecConfigLoading, setIsSpecConfigLoading] = useState(false);
  const [formDataConfig, setFormDataConfig] = useState({});
  const [selectedId, setSelectedId] = useState("");
  const [selectedItemName, setSelectedItemName] = useState("");
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
      if (prevInputOptions.some((opt) => opt.value === inputOption.value)) {
        return prevInputOptions; // Return previous state unchanged
      } else {
        // Create a new array with the existing options and the new option
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
    if (type === "output") {
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

    if (type === "input") {
      // Remove Database from Source Dropdown
      const filteredOptions = inputOptions.filter(
        (option) =>
          option.value !== "DATABASE" && option.value !== "APPDEPLOYMENT"
      );
      setOptions(filteredOptions);
    }
  }, [source, destination]);

  useEffect(() => {
    if (endpointDetails?.connection_type !== connType) {
      setConnType(endpointDetails?.connection_type);
    }

    if (!endpointDetails?.connector_instance) {
      setConnDetails({});
      return;
    }

    // Use connector_instance data directly from endpointDetails if it's an object
    if (typeof endpointDetails?.connector_instance === "object") {
      const connectorData = endpointDetails.connector_instance;
      connectorData.connector_metadata = connectorData.connector_metadata || {};
      connectorData.connector_metadata.connectorName =
        connectorData?.connector_name || "";
      setConnDetails(connectorData);
      setSelectedId(connectorData?.connector_id);
      return;
    }

    // Fallback for legacy connector_instance ID format (string)
    if (typeof endpointDetails?.connector_instance === "string") {
      // Only call getSourceDetails if we haven't already loaded this connector
      if (connDetails?.id !== endpointDetails?.connector_instance) {
        getSourceDetails();
      }
      return;
    }
  }, [endpointDetails]);

  useEffect(() => {
    const menuItems = [];
    [...listOfConnectors].forEach((item) => {
      if (
        endpointDetails?.connection_type &&
        item?.connector_mode.split("_").join("") !==
          endpointDetails?.connection_type
      ) {
        return;
      }
      menuItems.push(
        getMenuItem(
          item?.name,
          item?.id,
          sourceIcon(item?.icon),
          undefined,
          undefined,
          item?.isDisabled
        )
      );
    });
    setSelectedId("");
    setFilteredList(menuItems);

    if (!endpointDetails?.id) {
      return;
    }

    setFormDataConfig(endpointDetails.configuration || {});
    const requestOptions = {
      method: "GET",
      url: getUrl(`workflow/endpoint/${endpointDetails?.id}/settings/`),
    };

    setIsSpecConfigLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSpecConfig(data?.schema || {});
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the spec"));
      })
      .finally(() => {
        setIsSpecConfigLoading(false);
      });
  }, [connType, listOfConnectors]);

  useEffect(() => {
    if (!type) {
      return;
    }

    const requestOptions = {
      method: "GET",
      url: getUrl(`supported_connectors/?type=${type.toUpperCase()}`),
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        let data = res?.data;
        // Remove items specified in needToRemove from data
        Object.keys(needToRemove).forEach((mode) => {
          const idsToRemove = needToRemove[mode];
          data = data.filter(
            (source) =>
              !(
                source.connector_mode === mode &&
                idsToRemove.includes(source.id)
              )
          );
        });

        const updatedSources = data?.map((source) => ({
          ...source,
          isDisabled: disabledIdsByType[source?.connector_mode]?.includes(
            source?.id
          ),
        }));
        setListOfConnectors(updatedSources || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {});
  }, [type]);

  const sourceIcon = (src) => {
    return <Image src={src} height={25} width={25} preview={false} />;
  };

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
    if (type === "input") {
      clearDestination({
        connection_type: "",
        connector_instance_id: null,
      });
    }
  };

  const handleUpdate = (updatedData, showSuccess) => {
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
        if (type === "input") {
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

  const getSourceDetails = () => {
    const requestOptions = {
      method: "GET",
      url: getUrl(`connector/${endpointDetails?.connector_instance}/`),
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        data["connector_metadata"]["connectorName"] =
          data?.connector_name || "";
        setConnDetails(data);
        setSelectedId(data?.connector_id);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
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
                    handleUpdate({
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
                    connType === "API" ||
                    connType === "APPDEPLOYMENT"
                  }
                >
                  {getConfigureButtonText()}
                </Button>
              </Tooltip>
            </Space>
          </SpaceWrapper>
        </Col>
      </Row>
      <ConfigureConnectorModal
        open={openModal}
        setOpen={setOpenModal}
        type={type}
        selectedId={selectedId}
        setSelectedId={setSelectedId}
        handleUpdate={handleUpdate}
        filteredList={filteredList}
        connectorMetadata={connDetails?.connector_metadata}
        connectorId={connDetails?.id}
        specConfig={specConfig}
        formDataConfig={formDataConfig}
        setFormDataConfig={setFormDataConfig}
        isSpecConfigLoading={isSpecConfigLoading}
        connDetails={connDetails}
        connType={connType}
        selectedItemName={selectedItemName}
        setSelectedItemName={setSelectedItemName}
        workflowDetails={details}
      />
    </>
  );
}

DsSettingsCard.propTypes = {
  type: PropTypes.string.isRequired,
  endpointDetails: PropTypes.object.isRequired,
  message: PropTypes.string,
};

export { DsSettingsCard };
