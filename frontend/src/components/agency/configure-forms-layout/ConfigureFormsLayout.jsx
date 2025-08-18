import { Col, Row, Typography } from "antd";
import PropTypes from "prop-types";

import { SettingsForm } from "../settings-form/SettingsForm";
import { AddSource } from "../../input-output/add-source/AddSource";
import { EmptyState } from "../../widgets/empty-state/EmptyState";

function ConfigureFormsLayout({
  selectedId,
  type,
  handleUpdate,
  editItemId,
  connectorMetadata,
  isConnAvailable,
  specConfig,
  formDataConfig,
  setFormDataConfig,
  isSpecConfigLoading,
  connDetails,
  connType,
  selectedItemName,
}) {
  return (
    <Row className="conn-modal-tab-body">
      <Col span={12} className="conn-modal-form-right">
        <div className="conn-modal-flex">
          <Typography.Text strong>Connection Settings</Typography.Text>
          <div className="conn-modal-gap" />
          <div className="conn-modal-flex-1">
            {!selectedId ? (
              <EmptyState
                text={
                  isConnAvailable
                    ? "Select the connector"
                    : "No Connector available"
                }
              />
            ) : (
              <AddSource
                selectedSourceId={selectedId}
                metadata={connectorMetadata}
                type={type}
                editItemId={editItemId}
                handleUpdate={handleUpdate}
                connDetails={connDetails}
                connType={connType}
                selectedSourceName={selectedItemName}
                formDataConfig={formDataConfig}
              />
            )}
          </div>
        </div>
      </Col>
      {connType !== "MANUALREVIEW" && (
        <Col span={12} className="conn-modal-form-left">
          <div className="conn-modal-flex">
            <Typography.Text strong>Configuration</Typography.Text>
            <div className="conn-modal-gap" />
            <div className="conn-modal-flex-1">
              {!specConfig || Object.keys(specConfig)?.length === 0 ? (
                <EmptyState text="Failed to load the configuration form" />
              ) : (
                <SettingsForm
                  selectedId={selectedId}
                  handleUpdate={handleUpdate}
                  spec={specConfig}
                  formData={formDataConfig}
                  setFormData={setFormDataConfig}
                  isLoading={isSpecConfigLoading}
                />
              )}
            </div>
          </div>
        </Col>
      )}
    </Row>
  );
}

ConfigureFormsLayout.propTypes = {
  selectedId: PropTypes.string.isRequired,
  type: PropTypes.string.isRequired,
  handleUpdate: PropTypes.func.isRequired,
  editItemId: PropTypes.string,
  connectorMetadata: PropTypes.object,
  isConnAvailable: PropTypes.bool.isRequired,
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
  connDetails: PropTypes.object,
  connType: PropTypes.string,
  selectedItemName: PropTypes.string,
};

export { ConfigureFormsLayout };
