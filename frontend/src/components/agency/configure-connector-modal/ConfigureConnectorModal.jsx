import { Col, Modal, Row, Tabs, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { ListOfConnectors } from "../list-of-connectors/ListOfConnectors";
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
}) {
  const [activeKey, setActiveKey] = useState("1");
  useEffect(() => {
    if (connectorMetadata && connType === "FILESYSTEM") {
      setActiveKey("2"); // If connector is already configured
    } else {
      setActiveKey("1"); // default value
    }
  }, [open, connectorMetadata]);

  // Auto-select the configured connector when modal opens
  useEffect(() => {
    if (open && connDetails?.connector_id && filteredList?.length > 0) {
      const configuredConnector = filteredList.find(
        (item) => item?.key === connDetails?.connector_id
      );

      if (configuredConnector) {
        setSelectedId(connDetails?.connector_id);
        setSelectedItemName(configuredConnector?.label);
      }
    }
  }, [open, connDetails, filteredList]);
  const { setPostHogCustomEvent, posthogConnectorEventText } =
    usePostHogEvents();

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
      if (prevTabOptions.some((opt) => opt?.key === tabOption?.key)) {
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
      if (item?.key === "2") {
        item.visible = connType === "FILESYSTEM";
        item.disabled =
          !connectorId ||
          connDetails?.connector_id !== selectedId ||
          connType === "DATABASE";
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
  }, [open, selectedId, connType, connectorId, connDetails]);

  useEffect(() => {
    const updatedTabItems = tabItems.map((item) => {
      if (item?.key === "MANUALREVIEW") {
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
  const handleSelectItem = (e) => {
    const id = e?.key;
    setSelectedId(id?.toString());
    setActiveKey("1");

    const connectorData = [...filteredList].find((item) => item?.key === id);
    setSelectedItemName(connectorData?.label);

    try {
      setPostHogCustomEvent(posthogConnectorEventText[`${connType}:${type}`], {
        info: `Selected a connector`,
        connector_name: connectorData?.label,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const onTabChange = (key) => {
    setActiveKey(key);
  };

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
        <div className="conn-modal-gap" />
        <Row className="conn-modal-row">
          <Col
            span={4}
            className="conn-modal-col conn-modal-col-left conn-modal-form-pad-right"
          >
            <ListOfConnectors
              listOfConnectors={filteredList}
              selectedId={selectedId}
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
  connectorMetadata: PropTypes.any,
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
  connDetails: PropTypes.object,
  connType: PropTypes.string,
  selectedItemName: PropTypes.string,
  setSelectedItemName: PropTypes.func.isRequired,
  workflowDetails: PropTypes.object,
};

export { ConfigureConnectorModal };
