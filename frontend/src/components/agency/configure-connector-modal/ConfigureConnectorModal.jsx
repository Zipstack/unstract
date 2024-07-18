import { Col, Modal, Row, Tabs, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { ListOfConnectors } from "../list-of-connectors/ListOfConnectors";
import "./ConfigureConnectorModal.css";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

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
}) {
  const [activeKey, setActiveKey] = useState("1");
  useEffect(() => {
    if (connectorMetadata) {
      setActiveKey("2"); // If connector is already configured
    } else {
      setActiveKey("1"); // default value
    }
  }, [open, connectorMetadata]);
  const { setPostHogCustomEvent, posthogConnectorEventText } =
    usePostHogEvents();
  const tabItems = [
    {
      key: "1",
      label: "Settings",
    },
    {
      key: "2",
      label: "File System",
      disabled:
        !connectorId ||
        connDetails?.connector_id !== selectedId ||
        connType === "DATABASE" ||
        connType === "MANUALREVIEW",
    },
  ];

  const handleSelectItem = (e) => {
    const id = e.key;
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
              items={tabItems}
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
            {activeKey === "2" && <ManageFiles selectedItem={connectorId} />}
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
  connectorMetadata: PropTypes.object.isRequired,
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
  connDetails: PropTypes.object,
  connType: PropTypes.string.isRequired,
  selectedItemName: PropTypes.string,
  setSelectedItemName: PropTypes.func.isRequired,
};

export { ConfigureConnectorModal };
