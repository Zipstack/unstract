import {
  ExclamationCircleOutlined,
  ExportOutlined,
  ImportOutlined,
  SettingOutlined,
  CheckCircleTwoTone,
} from "@ant-design/icons";
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

import { getMenuItem, titleCase } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { ConfigureConnectorModal } from "../configure-connector-modal/ConfigureConnectorModal";
import { SharedConnectorModal } from "../../connectors/SharedConnectorModal";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DsSettingsCard.css";

const tooltip = {
  input: "Data Source Settings",
  output: "Data Destination Settings",
};

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

  // Shared connector state
  const [sharedConnectors, setSharedConnectors] = useState([]);
  const [selectedSharedConnector, setSelectedSharedConnector] = useState(null);
  const [showSharedConnectors, setShowSharedConnectors] = useState(false);
  const [openSharedModal, setOpenSharedModal] = useState(false);
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

  const icons = {
    input: <ImportOutlined className="ds-set-icon-size" />,
    output: <ExportOutlined className="ds-set-icon-size" />,
  };

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

    if (!endpointDetails?.connector_instance?.length) {
      setConnDetails({});
      setSelectedSharedConnector(null);
      return;
    }

    if (connDetails?.id === endpointDetails?.connector_instance) {
      return;
    }

    getSourceDetails();
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
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${endpointDetails?.id}/settings/`,
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
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/supported_connectors/?type=${type.toUpperCase()}`,
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

  // Load shared connectors when connection type is selected
  useEffect(() => {
    if (connType && connType !== "API" && connType !== "APPDEPLOYMENT") {
      loadSharedConnectors();
    } else {
      setSharedConnectors([]);
      setSelectedSharedConnector(null);
      setShowSharedConnectors(false);
    }
  }, [connType]);

  const loadSharedConnectors = async () => {
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${
          sessionDetails?.orgId
        }/shared-connectors/by-type/?type=${type.toUpperCase()}`
      );

      // If no connType is set or if we have connectors, show them
      // The filtering should be more lenient to avoid showing "No connectors available"
      // when connectors actually exist and are usable
      let filtered = response.data || [];

      // Only apply strict filtering if connType is specifically set
      if (connType && (connType === "FILESYSTEM" || connType === "DATABASE")) {
        filtered = response.data.filter((connector) => {
          if (connType === "FILESYSTEM") {
            return connector.connector_mode === 1; // FILE_SYSTEM
          } else if (connType === "DATABASE") {
            return connector.connector_mode === 2; // DATABASE
          }
          return false;
        });

        // If strict filtering removes all connectors but we have connectors available,
        // fall back to showing all connectors rather than showing "No connectors available"
        if (filtered.length === 0 && response.data.length > 0) {
          filtered = response.data;
        }
      }

      setSharedConnectors(filtered);
      setShowSharedConnectors(filtered.length > 0);
    } catch (error) {
      console.error("Error loading shared connectors:", error);
      setSharedConnectors([]);
      setShowSharedConnectors(false);
    }
  };

  const handleSharedConnectorSelect = async (connectorId) => {
    if (connectorId === null) {
      // Clear selected connector to create a new one
      setSelectedSharedConnector(null);
      setConnDetails({});
      setSelectedId("");
      setSelectedItemName("");
      setFormDataConfig({});
      return;
    }

    const connector = sharedConnectors.find((c) => c.id === connectorId);
    if (connector) {
      setSelectedSharedConnector(connector);

      // Update the workflow endpoint to use this shared connector
      try {
        await handleUpdate({
          connection_type: connType,
          connector_instance: connectorId,
        });

        // Update local state to show the connector as configured
        setConnDetails(connector);
        setSelectedId(connector.connector_id);
        setSelectedItemName(connector.connector_name);

        // Load the connector's configuration
        if (connector.configuration) {
          setFormDataConfig(connector.configuration);
        }

        setAlertDetails({
          type: "success",
          content: "Connector updated successfully",
        });
      } catch (error) {
        console.error("Error updating connector:", error);
        setAlertDetails({
          type: "error",
          content: "Failed to update connector",
        });
      }
    }
  };

  const handleSharedConnectorSaved = () => {
    setOpenSharedModal(false);
    // Reload shared connectors to include the new one
    loadSharedConnectors();
    setAlertDetails({
      type: "success",
      content: "Shared connector created successfully",
    });
  };

  const handleSettingsClick = () => {
    if (showSharedConnectors) {
      // Always use the workflow configuration modal when shared connectors are enabled
      // This will show shared connectors list and allow creating new ones if needed
      setOpenModal(true);
    } else {
      // Use the original workflow-specific connector modal for legacy workflows
      setOpenModal(true);
    }
  };

  const sourceIcon = (src) => {
    return <Image src={src} height={25} width={25} preview={false} />;
  };

  const clearDestination = (updatedData) => {
    const body = { ...destination, ...updatedData };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${destination?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
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
        connector_instance: null,
      });
    }
  };

  const handleUpdate = (updatedData, showSuccess) => {
    const body = { ...endpointDetails, ...updatedData };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${endpointDetails?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
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
      url: `/api/v1/unstract/${sessionDetails?.orgId}/connector/${endpointDetails?.connector_instance}/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        data["connector_metadata"]["connectorName"] =
          data?.connector_name || "";
        setConnDetails(data);
        setSelectedId(data?.connector_id);

        // Check if this is a shared connector
        if (data?.is_shared && data?.workflow === null) {
          setSelectedSharedConnector(data);
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  return (
    <>
      {/* No connectors available message - displayed above the bordered card */}
      {showSharedConnectors && sharedConnectors.length === 0 && (
        <div
          style={{
            padding: "8px 12px 4px 12px",
            backgroundColor: "#F8FBFF",
            borderTop: "1px solid #D4D4D4",
            borderLeft: "1px solid #D4D4D4",
            borderRight: "1px solid #D4D4D4",
            borderTopLeftRadius: "8px",
            borderTopRightRadius: "8px",
          }}
        >
          <Typography.Text
            type="secondary"
            style={{
              fontSize: 12,
              display: "block",
              textAlign: "left",
            }}
          >
            No connectors available
          </Typography.Text>
        </div>
      )}

      <Row
        className="ds-set-card-row"
        style={{
          border: "1px solid #D4D4D4",
          borderTop:
            showSharedConnectors && sharedConnectors.length === 0
              ? "none"
              : "1px solid #D4D4D4",
          borderRadius:
            showSharedConnectors && sharedConnectors.length === 0
              ? "0px 0px 8px 8px"
              : "8px",
        }}
      >
        <Col span={4} className="ds-set-card-col1">
          <Tooltip title={tooltip[type]}>{icons[type]}</Tooltip>
        </Col>
        <Col span={16} className="ds-set-card-col2">
          <SpaceWrapper>
            <Space direction="horizontal" wrap={false} align="center">
              <Tooltip
                title={
                  !allowChangeEndpoint &&
                  "Workflow used in API/Task/ETL deployment"
                }
              >
                <Select
                  className="ds-set-card-select"
                  size="small"
                  options={options}
                  placeholder="Select Connector Type"
                  value={endpointDetails?.connection_type || undefined}
                  disabled={!allowChangeEndpoint}
                  onChange={(value) => {
                    handleUpdate({
                      connection_type: value,
                      connector_instance: null,
                    });
                    updateDestination();
                  }}
                />
              </Tooltip>
            </Space>
            <div className="display-flex-align-center">
              {connDetails?.connector_name ? (
                <Space>
                  <Image
                    src={connDetails?.icon}
                    height={20}
                    width={20}
                    preview={false}
                  />
                  <Typography.Text className="font-size-12">
                    {connDetails?.connector_name}
                  </Typography.Text>
                </Space>
              ) : (
                <>
                  {connType === "API" || connType === "APPDEPLOYMENT" ? (
                    <Typography.Text
                      className="font-size-12 display-flex-align-center"
                      ellipsis={{ rows: 1, expandable: false }}
                      type="secondary"
                    >
                      <CheckCircleTwoTone twoToneColor="#52c41a" />
                      <span style={{ marginLeft: "5px" }}>
                        {titleCase(type)} set to {connType} successfully
                      </span>
                    </Typography.Text>
                  ) : (
                    <Typography.Text
                      className="font-size-12 display-flex-align-center"
                      ellipsis={{ rows: 1, expandable: false }}
                      type="secondary"
                    >
                      <ExclamationCircleOutlined />
                      <span style={{ marginLeft: "5px" }}>
                        Connector not configured
                      </span>
                    </Typography.Text>
                  )}
                </>
              )}
            </div>
            <div style={{ marginTop: 4 }}>
              <Typography.Paragraph
                ellipsis={{ rows: 2, expandable: false }}
                className="font-size-12"
                type="secondary"
                style={{ marginBottom: 0 }}
              >
                {message}
              </Typography.Paragraph>
            </div>
          </SpaceWrapper>
        </Col>
        <Col span={4} className="ds-set-card-col3">
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: "100%",
            }}
          >
            <Tooltip
              title={
                showSharedConnectors && sharedConnectors.length > 0
                  ? "Create new connector"
                  : endpointDetails?.connection_type
                  ? "Configure connector"
                  : "Select the connector type from the dropdown"
              }
            >
              <Button
                type="text"
                size="small"
                onClick={handleSettingsClick}
                disabled={
                  !endpointDetails?.connection_type ||
                  connType === "API" ||
                  connType === "APPDEPLOYMENT"
                }
              >
                <SettingOutlined />
              </Button>
            </Tooltip>
          </div>
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
        showSharedConnectors={showSharedConnectors}
        sharedConnectors={sharedConnectors}
        selectedSharedConnector={selectedSharedConnector}
        handleSharedConnectorSelect={handleSharedConnectorSelect}
      />

      <SharedConnectorModal
        open={openSharedModal}
        onCancel={() => setOpenSharedModal(false)}
        onSave={handleSharedConnectorSaved}
        connectorData={null}
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
