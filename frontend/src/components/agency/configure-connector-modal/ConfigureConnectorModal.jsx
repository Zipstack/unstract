import { Col, Modal, Row, Typography, Select, Space, Image, Tabs } from "antd";
import { CloudDownloadOutlined, CloudUploadOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import useRequestUrl from "../../../hooks/useRequestUrl";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import "./ConfigureConnectorModal.css";

let DBRules;

try {
  DBRules =
    require("../../../plugins/manual-review/db-rules/DBRules.jsx").DBRules;
} catch {
  // The component will remain null of it is not available
}
function ConfigureConnectorModal({
  open,
  setOpen,
  connDetails,
  setConnDetails,
  connType,
  connMode,
  workflowDetails,
  handleEndpointUpdate,
  endpointDetails,
  formDataConfig,
  setFormDataConfig,
}) {
  const [availableConnectors, setAvailableConnectors] = useState([]);
  const [addNewOption, setAddNewOption] = useState(null);
  const [isLoadingConnectors, setIsLoadingConnectors] = useState(false);
  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [activeTabKey, setActiveTabKey] = useState("1");
  const [tabItems, setTabItems] = useState([
    {
      key: "1",
      label: "Settings",
      visible: true,
    },
  ]);
  const [specConfig, setSpecConfig] = useState({});
  const [isSpecConfigLoading, setIsSpecConfigLoading] = useState(false);

  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const { getUrl } = useRequestUrl();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent, posthogConnectorEventText } =
    usePostHogEvents();

  const setUpdatedTabOptions = (tabOption) => {
    setTabItems((prevTabOptions) => {
      // Check if tabOption already exists in prevTabOptions
      // Return previous state unchanged if it does or create new array
      if (prevTabOptions.some((opt) => opt?.key === tabOption?.key)) {
        return prevTabOptions;
      } else {
        const updatedTabOptions = [...prevTabOptions, tabOption];
        return updatedTabOptions;
      }
    });
  };

  const onTabChange = (key) => {
    setActiveTabKey(key);
  };

  // Load plugin tab for Human In The Loop (DATABASE connectors only)
  useEffect(() => {
    if (connMode !== "DATABASE") {
      return;
    }

    try {
      const tabOption =
        require("../../../plugins/manual-review/connector-config-tab-mrq/ConnectorConfigTabMRQ").mrqTabs;
      if (tabOption) {
        tabOption["disabled"] = !connDetails?.id;
        tabOption["visible"] = true;
        setUpdatedTabOptions(tabOption);
      }
    } catch {
      // The component will remain null if it is not available
    }
  }, [connMode, connDetails?.id]);

  const fetchEndpointConfigSchema = () => {
    if (!endpointDetails?.id) {
      return;
    }

    const requestOptions = {
      method: "GET",
      url: getUrl(`workflow/endpoint/${endpointDetails.id}/settings/`),
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
  };

  const fetchAvailableConnectors = (connectionType) => {
    if (!connectionType || connectionType === "API") {
      setAvailableConnectors([]);
      return;
    }

    setIsLoadingConnectors(true);

    const requestOptions = {
      method: "GET",
      url: getUrl(`connector/?connector_mode=${connectionType}`),
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        const connectors = response?.data || [];

        // Separate regular connectors from "Add new connector" option
        const regularConnectors = connectors.map((conn) => ({
          value: conn.id,
          label: conn.connector_name,
          icon: conn.icon,
          connector: conn,
        }));

        // Keep "Add new connector" separate for sticky positioning
        const addNewOption = {
          value: "add_new",
          label: "+ Add new connector",
          isAddNew: true,
        };

        // For the Select options, only include regular connectors
        const options = regularConnectors;

        setAvailableConnectors(options);
        setAddNewOption(addNewOption);
      })
      .catch((error) => {
        setAvailableConnectors([]);
        setAlertDetails(handleException(error, "Failed to load connectors"));
      })
      .finally(() => {
        setIsLoadingConnectors(false);
      });
  };

  const handleConnectorSelect = (value) => {
    if (value === "add_new") {
      setShowAddSourceModal(true);
    } else {
      // Find the selected connector from availableConnectors to get its details
      const selectedConnector = availableConnectors.find(
        (conn) => conn.value === value
      );
      if (selectedConnector && selectedConnector.connector) {
        // Update connDetails with connector info
        setConnDetails(selectedConnector.connector);

        // Track connector selection with PostHog
        try {
          setPostHogCustomEvent(
            posthogConnectorEventText[`${connMode}:${connType}`],
            {
              info: `Selected a connector`,
              connector_name: selectedConnector.connector.connector_name,
            }
          );
        } catch (err) {
          // If an error occurs while setting custom posthog event, ignore it and continue
        }
      }

      // Update endpoint with the selected connector
      handleEndpointUpdate({
        connector_instance_id: selectedConnector.connector.id,
      });
    }
  };

  const handleConnectorCreated = (newConnectorData) => {
    setShowAddSourceModal(false);

    if (newConnectorData) {
      const newConnectorOption = {
        value: newConnectorData.id,
        label: newConnectorData.connector_name,
        icon: newConnectorData.icon,
        connector: newConnectorData,
      };

      // Simply add the new connector to the existing list
      setAvailableConnectors((prev) => [...prev, newConnectorOption]);

      // Update connDetails to select the new connector
      setConnDetails(newConnectorData);
    }
  };

  // Fetch available connectors when modal opens and connection type is available
  useEffect(() => {
    if (open) {
      fetchAvailableConnectors(connMode);
      fetchEndpointConfigSchema();
    }
  }, [open, connMode]);

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      width={1200}
      maskClosable={false}
    >
      <div className="conn-modal-body">
        <Typography.Text className="modal-header" strong>
          Configure Connector
        </Typography.Text>

        {/* Connector Selection Dropdown */}
        <div className="connector-selection-section">
          <Typography.Text strong style={{ display: "block", marginBottom: 8 }}>
            Select Connector
          </Typography.Text>
          <Select
            className="connector-selection-dropdown"
            placeholder="Select a connector"
            showSearch
            filterOption={(input, option) => {
              return option?.data?.label
                ?.toLowerCase()
                .includes(input.toLowerCase());
            }}
            value={
              connDetails?.id
                ? {
                    value: connDetails.id,
                    label: (() => {
                      const selectedConnector = availableConnectors.find(
                        (conn) => conn.value === connDetails.id
                      );
                      return (
                        <Space>
                          {selectedConnector?.icon &&
                            !selectedConnector?.isAddNew && (
                              <Image
                                src={selectedConnector.icon}
                                width={20}
                                height={20}
                                preview={false}
                              />
                            )}
                          <span>{selectedConnector?.label}</span>
                        </Space>
                      );
                    })(),
                  }
                : undefined
            }
            labelInValue
            onChange={(option) => handleConnectorSelect(option?.value)}
            loading={isLoadingConnectors}
            options={availableConnectors.map((conn) => ({
              value: conn.value,
              label: (
                <Space>
                  {conn.icon && !conn.isAddNew && (
                    <Image
                      src={conn.icon}
                      width={20}
                      height={20}
                      preview={false}
                    />
                  )}
                  <span>{conn.label}</span>
                </Space>
              ),
              data: conn,
            }))}
            style={{ width: "100%" }}
            optionRender={(option) => option.label}
            dropdownRender={(menu) => (
              <>
                <div style={{ maxHeight: 200, overflowY: "auto" }}>{menu}</div>
                {addNewOption && (
                  <div
                    className="connector-dropdown-add-new"
                    onClick={() => handleConnectorSelect("add_new")}
                  >
                    <Space>
                      <span>{addNewOption.label}</span>
                    </Space>
                  </div>
                )}
              </>
            )}
          />
        </div>

        {/* Show placeholder when no connector is selected */}
        {!connDetails?.id && (
          <div className="connector-placeholder">
            {connType === "input" ? (
              <CloudDownloadOutlined className="connector-placeholder-icon" />
            ) : (
              <CloudUploadOutlined className="connector-placeholder-icon" />
            )}
            <Typography.Text className="connector-placeholder-text">
              Select an existing connector or create a new connector to continue
            </Typography.Text>
          </div>
        )}

        {/* Only show configuration form and file browser after a connector is selected */}
        {connDetails?.id && (
          <>
            {/* DATABASE connectors: Show tabs with Settings and Human In The Loop */}
            {connMode === "DATABASE" ? (
              <Tabs
                activeKey={activeTabKey}
                onChange={onTabChange}
                className="conn-modal-col"
                items={tabItems
                  .filter((item) => item.visible !== false)
                  .map((item) => ({
                    key: item.key,
                    label: item.label,
                    disabled: item.disabled,
                    children: (
                      <>
                        {item.key === "1" && (
                          <ConfigureFormsLayout
                            handleUpdate={handleEndpointUpdate}
                            specConfig={specConfig}
                            formDataConfig={formDataConfig}
                            setFormDataConfig={setFormDataConfig}
                            isSpecConfigLoading={isSpecConfigLoading}
                          />
                        )}
                        {item.key === "MANUALREVIEW" && DBRules && (
                          <DBRules workflowDetails={workflowDetails} />
                        )}
                      </>
                    ),
                  }))}
              />
            ) : (
              /* Other connector types: Show existing layout */
              <Row className="conn-modal-row" gutter={24}>
                {/* Left side - Configuration Form */}
                <Col span={12} className="conn-modal-col">
                  <div className="conn-modal-fs-config">
                    <ConfigureFormsLayout
                      handleUpdate={handleEndpointUpdate}
                      specConfig={specConfig}
                      formDataConfig={formDataConfig}
                      setFormDataConfig={setFormDataConfig}
                      isSpecConfigLoading={isSpecConfigLoading}
                    />
                  </div>
                </Col>

                {/* Right side - File System Browser (only for FILESYSTEM connectors) */}
                {connMode === "FILESYSTEM" && connDetails?.id && (
                  <Col span={12} className="conn-modal-col">
                    <div className="file-browser-section">
                      <Typography.Text strong style={{ display: "block" }}>
                        Browse Files & Folders
                      </Typography.Text>
                      <ManageFiles selectedItem={connDetails?.id} />
                    </div>
                  </Col>
                )}
              </Row>
            )}
          </>
        )}
      </div>

      {/* Add Source Modal for creating new connectors */}
      {showAddSourceModal && (
        <AddSourceModal
          open={showAddSourceModal}
          setOpen={setShowAddSourceModal}
          sourceType="connectors"
          type={connType}
          addNewItem={handleConnectorCreated}
          editItemId={null}
          setEditItemId={() => {}}
        />
      )}
    </Modal>
  );
}

ConfigureConnectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  connDetails: PropTypes.object,
  setConnDetails: PropTypes.func.isRequired,
  connType: PropTypes.string.isRequired,
  connMode: PropTypes.string.isRequired,
  workflowDetails: PropTypes.object.isRequired,
  handleEndpointUpdate: PropTypes.func.isRequired,
  endpointDetails: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
};

export { ConfigureConnectorModal };
