import {
  Col,
  Modal,
  Row,
  Typography,
  Select,
  Space,
  Image,
  Tabs,
  Button,
} from "antd";
import { CloudDownloadOutlined, CloudUploadOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useEffect, useState, useRef, useCallback } from "react";
import { isEqual, cloneDeep } from "lodash";

import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import useRequestUrl from "../../../hooks/useRequestUrl";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
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
  const [isSavingEndpoint, setIsSavingEndpoint] = useState(false);
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
  const [selectedFolderPath, setSelectedFolderPath] = useState("");
  const [isFolderSelected, setIsFolderSelected] = useState(false);
  const [isPathFromFileBrowser, setIsPathFromFileBrowser] = useState(false);
  const [initialFormDataConfig, setInitialFormDataConfig] = useState({});
  const [initialConnectorId, setInitialConnectorId] = useState(null);
  const [showUnsavedChangesModal, setShowUnsavedChangesModal] = useState(false);

  const fileExplorerRef = useRef(null);
  const formRef = useRef(null);

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

  const onDBConfigTabChange = (key) => {
    setActiveTabKey(key);
  };

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
          value: conn?.id,
          label: conn?.connector_name,
          icon: conn?.icon,
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
      const selectedConnector = availableConnectors.find(
        (conn) => conn.value === value
      );
      if (selectedConnector?.connector) {
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

      // Select the new connector
      handleConnectorSelect(newConnectorData.id);
    }
  };

  const handleFolderSelect = (folderPath, itemType) => {
    setSelectedFolderPath(folderPath);
    setIsFolderSelected(itemType === "folder");
    setIsPathFromFileBrowser(true);
  };

  const handleAddFolder = () => {
    if (!selectedFolderPath) return;

    // HACK: For GDrive connectors, strip the "root/" prefix to avoid duplication
    // since backend will add it back during execution. This helps avoid a migration
    let folderPath = selectedFolderPath;
    if (
      isPathFromFileBrowser &&
      connDetails?.connector_id?.startsWith("gdrive") &&
      folderPath.startsWith("root/")
    ) {
      folderPath = folderPath.substring(5); // Remove "root/" prefix
    }

    if (connType === "input") {
      // SOURCE mode: Add to folders array (existing behavior)
      const currentFolders = formDataConfig?.folders || [];
      if (!currentFolders.includes(folderPath)) {
        setFormDataConfig((prev) => ({
          ...prev,
          folders: [...currentFolders, folderPath],
        }));
      }
    } else if (connType === "output") {
      // DESTINATION mode: Set outputFolder as single value
      setFormDataConfig((prev) => ({
        ...prev,
        outputFolder: folderPath,
      }));
    }

    setSelectedFolderPath("");
    setIsFolderSelected(false);
    setIsPathFromFileBrowser(false);
  };

  // Configuration for UI text based on connector type
  const folderSectionConfig = {
    input: {
      title: "Select Folder to Process",
      description: "Browse and select a folder to add to processing",
      buttonText: "Add Folder",
    },
    output: {
      title: "Select Output Folder",
      description: "Browse and select a folder for output files",
      buttonText: "Select Folder",
    },
  };

  const currentConfig =
    folderSectionConfig[connType] || folderSectionConfig.input;

  const hasUnsavedChanges = () => {
    const hasConfigChanges = !isEqual(formDataConfig, initialFormDataConfig);
    const hasConnectorChanged = connDetails?.id !== initialConnectorId;
    return hasConfigChanges || hasConnectorChanged;
  };

  const handleValidateAndSubmit = async (validatedFormData) => {
    const hasConfigChanges = !isEqual(validatedFormData, initialFormDataConfig);
    const hasConnectorChanged = connDetails?.id !== initialConnectorId;
    const hasChanges = hasConfigChanges || hasConnectorChanged;

    if (hasChanges && connDetails?.id) {
      setIsSavingEndpoint(true);
      try {
        const updatePayload = {};
        if (hasConnectorChanged) {
          updatePayload.connector_instance_id = connDetails.id;
        }
        if (hasConfigChanges) {
          updatePayload.configuration = validatedFormData;
        }
        if (Object.keys(updatePayload).length > 0) {
          await handleEndpointUpdate(updatePayload);
        }
        // Update initial values after successful save
        setInitialFormDataConfig(cloneDeep(validatedFormData));
        setInitialConnectorId(connDetails?.id);
        setAlertDetails({
          type: "success",
          content: "Configuration saved successfully.",
        });
      } catch (error) {
        setAlertDetails({
          type: "error",
          content:
            error?.message || "Failed to save changes. Please try again.",
        });
      } finally {
        setIsSavingEndpoint(false);
      }
    }
  };

  const handleSave = async () => {
    const hasConfigChanges = !isEqual(formDataConfig, initialFormDataConfig);

    if (hasConfigChanges && formRef?.current) {
      if (formRef?.current?.validateForm()) {
        await handleValidateAndSubmit(formDataConfig);
        return true;
      } else {
        // RJSF shows validation errors
        return false;
      }
    } else {
      // No config changes, just save connector changes if any
      await handleValidateAndSubmit(formDataConfig);
      return true;
    }
  };

  const handleModalClose = () => {
    if (hasUnsavedChanges()) {
      setShowUnsavedChangesModal(true);
    } else {
      setOpen(false);
    }
  };

  const handleConfirmClose = () => {
    const hasConfigChanges = !isEqual(formDataConfig, initialFormDataConfig);
    const hasConnectorChanged = connDetails?.id !== initialConnectorId;

    // Reset form data to original DB values only if changed
    if (hasConfigChanges) {
      setFormDataConfig(cloneDeep(initialFormDataConfig));
    }

    // Reset connector to original selection only if changed
    if (hasConnectorChanged) {
      if (initialConnectorId && availableConnectors.length > 0) {
        const originalConnector = availableConnectors.find(
          (conn) => conn.value === initialConnectorId
        );
        if (originalConnector?.connector) {
          setConnDetails(originalConnector.connector);
        }
      } else if (!initialConnectorId) {
        // If no initial connector, reset to no selection
        setConnDetails(null);
      }
    }

    setShowUnsavedChangesModal(false);
    // Delay closing the main modal to allow confirmation modal to close first
    setTimeout(() => setOpen(false), 0);
  };

  const handleSaveAndClose = async () => {
    const saveSuccessful = await handleSave();
    setShowUnsavedChangesModal(false);
    if (saveSuccessful) {
      // Delay closing the main modal to allow confirmation modal to close first
      setTimeout(() => setOpen(false), 0);
    }
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

  // Handle click-outside to clear file selection
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        fileExplorerRef.current &&
        !fileExplorerRef.current.contains(event.target)
      ) {
        setSelectedFolderPath("");
        setIsFolderSelected(false);
        setIsPathFromFileBrowser(false);
      }
    };

    if (open && connMode === "FILESYSTEM") {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open, connMode]);

  // Fetch available connectors when modal opens and connection type is available
  useEffect(() => {
    if (open) {
      fetchAvailableConnectors(connMode);
      fetchEndpointConfigSchema();
    }
  }, [open, connMode]);

  // Capture initial configuration and connector when modal opens
  useEffect(() => {
    if (open) {
      if (endpointDetails?.configuration) {
        setInitialFormDataConfig(cloneDeep(endpointDetails.configuration));
      }
      setInitialConnectorId(endpointDetails?.connector_instance?.id || null);
    } else {
      setInitialFormDataConfig({});
      setInitialConnectorId(null);
    }
  }, [
    open,
    endpointDetails?.configuration,
    endpointDetails?.connector_instance,
  ]);

  // Helper function to render connector label
  const renderConnectorLabel = (connDetails, availableConnectors) => {
    if (!connDetails?.id) return undefined;

    const selectedConnector = availableConnectors.find(
      (conn) => conn.value === connDetails.id
    );

    return (
      <Space>
        {selectedConnector?.icon && !selectedConnector?.isAddNew && (
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
  };

  // Memoized dropdown render function
  const renderDropdown = useCallback(
    (menu) => (
      <>
        <div className="connector-dropdown-menu-container">{menu}</div>
        {addNewOption && (
          <button
            className="connector-dropdown-add-new"
            onClick={() => handleConnectorSelect("add_new")}
            type="button"
            aria-label="Add new connector"
          >
            <Space>
              <span>{addNewOption.label}</span>
            </Space>
          </button>
        )}
      </>
    ),
    [addNewOption, handleConnectorSelect]
  );

  return (
    <Modal
      open={open}
      onCancel={handleModalClose}
      confirmLoading={isSavingEndpoint}
      closable={!isSavingEndpoint}
      centered
      footer={
        connDetails?.id ? (
          <div className="conn-modal-footer">
            <Button onClick={handleModalClose}>Cancel</Button>
            <Button
              type="primary"
              loading={isSavingEndpoint}
              onClick={handleSave}
              disabled={!hasUnsavedChanges()}
            >
              Save
            </Button>
          </div>
        ) : null
      }
      width={1200}
      maskClosable={false}
    >
      <div className="conn-modal-body">
        <Typography.Text className="modal-header" strong>
          Configure Connector
        </Typography.Text>

        {/* Connector Selection Dropdown */}
        <div className="connector-selection-section">
          <Typography.Text strong className="connector-selection-label">
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
                    label: renderConnectorLabel(
                      connDetails,
                      availableConnectors
                    ),
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
            optionRender={(option) => option.label}
            dropdownRender={renderDropdown}
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
                onChange={onDBConfigTabChange}
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
                            specConfig={specConfig}
                            formDataConfig={formDataConfig}
                            setFormDataConfig={setFormDataConfig}
                            isSpecConfigLoading={isSpecConfigLoading}
                            formRef={formRef}
                            validateAndSubmit={handleValidateAndSubmit}
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
                      specConfig={specConfig}
                      formDataConfig={formDataConfig}
                      setFormDataConfig={setFormDataConfig}
                      isSpecConfigLoading={isSpecConfigLoading}
                      formRef={formRef}
                      validateAndSubmit={handleValidateAndSubmit}
                    />
                  </div>
                </Col>

                {/* Right side - File System Browser (only for FILESYSTEM connectors) */}
                {connMode === "FILESYSTEM" && connDetails?.id && (
                  <Col span={12} className="conn-modal-col form-right">
                    <div className="file-browser-section" ref={fileExplorerRef}>
                      <div className="file-browser-header">
                        <div className="file-browser-content">
                          <Typography.Text strong style={{ display: "block" }}>
                            {currentConfig.title}
                          </Typography.Text>
                          <Typography.Text
                            type="secondary"
                            className="field-description"
                          >
                            {currentConfig.description}
                          </Typography.Text>
                        </div>
                        <CustomButton
                          type="primary"
                          size="small"
                          disabled={!isFolderSelected}
                          onClick={handleAddFolder}
                        >
                          {currentConfig.buttonText}
                        </CustomButton>
                      </div>
                      <ManageFiles
                        selectedConnector={connDetails?.id}
                        onFolderSelect={handleFolderSelect}
                        selectedFolderPath={selectedFolderPath}
                      />
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
          isConnector={true}
          type={connType}
          connectorMode={connMode}
          addNewItem={handleConnectorCreated}
          editItemId={null}
          setEditItemId={() => {}}
        />
      )}

      {/* Unsaved Changes Confirmation Modal */}
      <Modal
        title="Unsaved Changes"
        open={showUnsavedChangesModal}
        onCancel={() => setShowUnsavedChangesModal(false)}
        footer={[
          <Button
            key="discard"
            onClick={handleConfirmClose}
            disabled={isSavingEndpoint}
          >
            Close without Saving
          </Button>,
          <Button
            key="save"
            type="primary"
            onClick={handleSaveAndClose}
            loading={isSavingEndpoint}
          >
            Save
          </Button>,
        ]}
        centered
      >
        You have unsaved changes. Do you want to save them before closing?
      </Modal>
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
