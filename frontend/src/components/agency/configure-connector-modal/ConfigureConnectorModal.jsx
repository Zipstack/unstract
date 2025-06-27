import {
  Col,
  Modal,
  Row,
  Tabs,
  Typography,
  Image,
  Button,
  Select,
  Space,
  Divider,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { ListOfConnectors } from "../list-of-connectors/ListOfConnectors";
import "./ConfigureConnectorModal.css";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { SettingsForm } from "../settings-form/SettingsForm";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

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
  type,
  selectedId,
  setSelectedId,
  handleUpdate,
  filteredList,
  connectorId,
  connectorMetadata,
  specConfig,
  formDataConfig,
  setFormDataConfig,
  isSpecConfigLoading,
  connDetails,
  connType,
  selectedItemName,
  setSelectedItemName,
  workflowDetails,
  showSharedConnectors = false,
  sharedConnectors = [],
  selectedSharedConnector = null,
  handleSharedConnectorSelect = () => {},
}) {
  const [activeKey, setActiveKey] = useState("1");
  const [showFileSystemPanel, setShowFileSystemPanel] = useState(false);
  const [selectedFolderPath, setSelectedFolderPath] = useState("");

  // Handler to show file system panel
  const handleAddFolderClick = () => {
    setShowFileSystemPanel(true);
  };

  // Handler to add selected folder to the folders list
  const handleSelectFolder = () => {
    console.log("handleSelectFolder called");
    console.log("selectedFolderPath:", selectedFolderPath);
    console.log("formDataConfig:", formDataConfig);

    if (selectedFolderPath && formDataConfig) {
      const currentFolders = formDataConfig.folders || [];
      const newFolders = [...currentFolders];

      // Only add if the folder is not already in the list
      if (!newFolders.includes(selectedFolderPath)) {
        newFolders.push(selectedFolderPath);
        const updatedConfig = {
          ...formDataConfig,
          folders: newFolders,
        };
        console.log("Updated config will be set:", updatedConfig);
        setFormDataConfig(updatedConfig);

        // Also save to the workflow immediately
        handleUpdate({ configuration: updatedConfig }, true);
      }

      // Hide the file system panel and reset selected path
      setShowFileSystemPanel(false);
      setSelectedFolderPath("");
    } else {
      console.log("No folder selected or no form data config");
    }
  };

  // Handler to receive selected folder path from file explorer
  const handleFolderSelect = (folderPath) => {
    console.log("Folder selected:", folderPath);
    setSelectedFolderPath(folderPath);
  };
  useEffect(() => {
    if (connectorMetadata && connType === "FILESYSTEM") {
      setActiveKey("2"); // If connector is already configured
    } else {
      setActiveKey("1"); // default value
    }
  }, [open, connectorMetadata]);
  const { setPostHogCustomEvent, posthogConnectorEventText } =
    usePostHogEvents();

  // Format shared connectors for ListOfConnectors component
  const formatSharedConnectors = () => {
    return sharedConnectors.map((connector) => ({
      key: connector.id,
      label: connector.connector_name,
      icon: null, // We can add icons later
      isDisabled: false,
    }));
  };

  // Determine which connector list to display
  const connectorListToShow = showSharedConnectors
    ? formatSharedConnectors()
    : filteredList;

  // Handle selection for both shared and regular connectors
  const handleSelectItem = (e) => {
    const id = e.key;

    if (showSharedConnectors) {
      // Handle shared connector selection
      handleSharedConnectorSelect(id);
      setActiveKey("2"); // Go directly to file browser for shared connectors
    } else {
      // Original logic for regular connectors
      setSelectedId(id?.toString());
      setActiveKey("1");

      const connectorData = [...filteredList].find((item) => item?.key === id);
      setSelectedItemName(connectorData?.label);

      try {
        setPostHogCustomEvent(
          posthogConnectorEventText[`${connType}:${type}`],
          {
            info: `Selected a connector`,
            connector_name: connectorData?.label,
          }
        );
      } catch (err) {
        // The key might not be available in the constant
      }
    }
  };

  const [tabItems, setTabItems] = useState([
    {
      key: "1",
      label: "Settings",
      visible: true,
    },
    {
      key: "2",
      label: "File System",
      disabled:
        !connectorId ||
        connDetails?.connector_id !== selectedId ||
        connType === "DATABASE",
      visible: false,
    },
  ]);
  const setUpdatedTabOptions = (tabOption) => {
    setTabItems((prevTabOptions) => {
      // Check if inputOption already exists in prevTabOptions
      if (prevTabOptions.some((opt) => opt.key === tabOption.key)) {
        return prevTabOptions; // Return previous state unchanged
      } else {
        // Create a new array with the existing options and the new option
        const updatedTabOptions = [...prevTabOptions, tabOption];
        return updatedTabOptions;
      }
    });
  };

  useEffect(() => {
    const updatedTabItems = tabItems.map((item) => {
      if (item.key === "2") {
        item.visible = connType === "FILESYSTEM";
      } else if (item.key === "MANUALREVIEW") {
        item.disabled =
          !connectorId || connDetails?.connector_id !== selectedId;
        item.visible = connType === "DATABASE" || connType === "MANUALREVIEW";
      } else {
        item.visible = true;
      }
      return item;
    });
    setTabItems(updatedTabItems);
  }, [open]);

  useEffect(() => {
    const updatedTabItems = tabItems.map((item) => {
      if (item.key === "MANUALREVIEW") {
        item.disabled =
          !connectorId || connDetails?.connector_id !== selectedId;
      }
      return item;
    });
    setTabItems(updatedTabItems);
  }, [connectorMetadata]);

  useEffect(() => {
    try {
      const tabOption =
        require("../../../plugins/manual-review/connector-config-tab-mrq/ConnectorConfigTabMRQ").mrqTabs;
      if (tabOption) {
        tabOption["disabled"] =
          !connectorId || connDetails?.connector_id !== selectedId;
        tabOption["visible"] = false;
        setUpdatedTabOptions(tabOption);
      }
    } catch {
      // The component will remain null of it is not available
    }
  }, []);

  const onTabChange = (key) => {
    setActiveKey(key);
  };

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      width={showFileSystemPanel ? 1200 : 800}
      maskClosable={false}
    >
      <div className="conn-modal-body">
        <Typography.Text className="modal-header" strong>
          {showSharedConnectors ? (
            <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              {(selectedSharedConnector?.icon || connDetails?.icon) && (
                <Image
                  src={selectedSharedConnector?.icon || connDetails?.icon}
                  height={20}
                  width={20}
                  preview={false}
                  style={{
                    display: "flex",
                    alignItems: "center",
                  }}
                />
              )}
              <span>
                {selectedSharedConnector?.connector_name ||
                  connDetails?.connector_name ||
                  "Shared Connector"}
              </span>
              <span>connector configuration</span>
            </span>
          ) : (
            <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              {(() => {
                const selectedConnector = filteredList.find(
                  (item) => item.key === selectedId
                );
                return (
                  selectedConnector?.icon && (
                    <span style={{ display: "flex", alignItems: "center" }}>
                      {selectedConnector.icon}
                    </span>
                  )
                );
              })()}
              <span>{selectedItemName || "Connector"}</span>
              <span>connector configuration</span>
            </span>
          )}
        </Typography.Text>
        <div className="conn-modal-gap" />
        {showSharedConnectors && (
          <>
            {/* Connector Selection Dropdown */}
            <div style={{ marginBottom: "16px" }}>
              <Typography.Text
                strong
                style={{ display: "block", marginBottom: "8px" }}
              >
                Select Existing Connector
              </Typography.Text>
              <Select
                style={{ width: "100%" }}
                placeholder="Choose an existing connector"
                value={selectedSharedConnector?.id || null}
                onChange={handleSharedConnectorSelect}
                allowClear
                size="middle"
              >
                {sharedConnectors.map((connector) => (
                  <Select.Option key={connector.id} value={connector.id}>
                    <Space>
                      {connector.icon && (
                        <Image
                          src={connector.icon}
                          height={16}
                          width={16}
                          preview={false}
                        />
                      )}
                      <span>{connector.connector_name}</span>
                    </Space>
                  </Select.Option>
                ))}
              </Select>
              <Typography.Text
                type="secondary"
                style={{ fontSize: "12px", display: "block", marginTop: "4px" }}
              >
                Select an existing connector to use its configuration, or clear
                the selection to create a new one
              </Typography.Text>
            </div>
            <Divider style={{ margin: "16px 0" }} />
          </>
        )}
        {showSharedConnectors ? (
          // New layout for shared connectors: Configuration and optional File browser
          <Row className="conn-modal-row">
            <Col
              span={showFileSystemPanel ? 12 : 24}
              className={`conn-modal-col ${
                showFileSystemPanel ? "conn-modal-form-pad-right" : ""
              }`}
            >
              <div style={{ marginBottom: "16px" }}>
                {connType === "FILESYSTEM" && (
                  <Button
                    size="small"
                    type="default"
                    onClick={handleAddFolderClick}
                    style={{ marginBottom: "16px" }}
                  >
                    Add Folder
                  </Button>
                )}
              </div>
              <SettingsForm
                key={`settings-form-${JSON.stringify(
                  formDataConfig?.folders || []
                )}`}
                selectedId={selectedSharedConnector?.connector_id || selectedId}
                handleUpdate={handleUpdate}
                spec={specConfig}
                formData={formDataConfig}
                setFormData={setFormDataConfig}
                isLoading={isSpecConfigLoading}
              />
            </Col>
            {showFileSystemPanel && connType === "FILESYSTEM" && (
              <Col
                span={12}
                className="conn-modal-col conn-modal-form-pad-left"
              >
                <div
                  style={{
                    marginBottom: "16px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <h3>Select Folder to Add to ETL</h3>
                    <p>Browse and select a folder to add to processing</p>
                  </div>
                  <div>
                    <Button
                      type="default"
                      onClick={() => setShowFileSystemPanel(false)}
                      style={{ marginRight: "8px" }}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="primary"
                      onClick={handleSelectFolder}
                      disabled={!selectedFolderPath}
                    >
                      Select Folder
                    </Button>
                  </div>
                </div>
                <ManageFiles
                  selectedItem={selectedSharedConnector?.id || connectorId}
                  onFolderSelect={handleFolderSelect}
                  selectedFolderPath={selectedFolderPath}
                />
              </Col>
            )}
          </Row>
        ) : (
          // Original layout for non-shared connectors
          <Row className="conn-modal-row">
            <Col
              span={4}
              className="conn-modal-col conn-modal-col-left conn-modal-form-pad-right"
            >
              <ListOfConnectors
                listOfConnectors={connectorListToShow}
                selectedId={
                  showSharedConnectors
                    ? selectedSharedConnector?.id
                    : selectedId
                }
                handleSelectItem={handleSelectItem}
              />
            </Col>
            <Col span={20} className="conn-modal-col conn-modal-form-pad-left">
              <Tabs
                activeKey={activeKey}
                items={tabItems.filter((item) => item?.visible !== false)}
                onChange={onTabChange}
                moreIcon={<></>}
              />
              {activeKey === "1" && (
                <ConfigureFormsLayout
                  selectedId={selectedId}
                  type={type}
                  handleUpdate={handleUpdate}
                  editItemId={connectorId}
                  connectorMetadata={connectorMetadata}
                  isConnAvailable={!!filteredList?.length}
                  specConfig={specConfig}
                  formDataConfig={formDataConfig}
                  setFormDataConfig={setFormDataConfig}
                  isSpecConfigLoading={isSpecConfigLoading}
                  connDetails={connDetails}
                  connType={connType}
                  selectedItemName={selectedItemName}
                />
              )}
              {activeKey === "2" && connType === "FILESYSTEM" && (
                <ManageFiles selectedItem={connectorId} />
              )}
              {activeKey === "MANUALREVIEW" && DBRules && (
                <DBRules
                  connDetails={connDetails}
                  workflowDetails={workflowDetails}
                />
              )}
            </Col>
          </Row>
        )}
      </div>
    </Modal>
  );
}

ConfigureConnectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  connectorId: PropTypes.string,
  selectedId: PropTypes.string,
  setSelectedId: PropTypes.func.isRequired,
  handleUpdate: PropTypes.func.isRequired,
  filteredList: PropTypes.array,
  connectorMetadata: PropTypes.object.isRequired,
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
  connDetails: PropTypes.object,
  connType: PropTypes.string.isRequired,
  selectedItemName: PropTypes.string,
  setSelectedItemName: PropTypes.func.isRequired,
  workflowDetails: PropTypes.object,
  showSharedConnectors: PropTypes.bool,
  sharedConnectors: PropTypes.array,
  selectedSharedConnector: PropTypes.object,
  handleSharedConnectorSelect: PropTypes.func,
};

export { ConfigureConnectorModal };
