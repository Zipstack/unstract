import { Col, Modal, Row, Tabs, Typography } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { ListOfConnectors } from "../list-of-connectors/ListOfConnectors";
import "./ConfigureConnectorModal.css";
import { ConfigureFormsLayout } from "../configure-forms-layout/ConfigureFormsLayout";
import { ManageFiles } from "../../input-output/manage-files/ManageFiles";

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
}) {
  const [activeKey, setActiveKey] = useState("1");

  const tabItems = [
    {
      key: "1",
      label: "Settings",
    },
    {
      key: "2",
      label: "File System",
      disabled: !connectorId || connDetails.connector_id !== selectedId,
    },
  ];

  const handleSelectItem = (e) => {
    const id = e.key;
    setSelectedId(id?.toString());
    setActiveKey("1");
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
};

export { ConfigureConnectorModal };
