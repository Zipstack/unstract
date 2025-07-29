import { Modal, Steps, Button, Typography } from "antd";
import PropTypes from "prop-types";
import { useState, useEffect } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ConfigureDs } from "../../input-output/configure-ds/ConfigureDs";
import { ConnectorListModal } from "../connector-list-modal/ConnectorListModal";

const { Title } = Typography;

function AddConnectorModal({ open, onCancel, onSave, connectorData = null }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [formData, setFormData] = useState({});
  const [spec, setSpec] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [availableConnectors, setAvailableConnectors] = useState([]);
  const [loadingConnectors, setLoadingConnectors] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (open) {
      fetchAvailableConnectors();
      if (connectorData) {
        // Editing existing connector
        // Find the connector in available connectors
        setFormData(connectorData.connector_metadata || {});
        setCurrentStep(1);
      } else {
        // Creating new connector
        reset();
      }
    }
  }, [open, connectorData]);

  const reset = () => {
    setCurrentStep(0);
    setSelectedConnector(null);
    setFormData({});
    setSpec({});
  };

  const fetchAvailableConnectors = async () => {
    setLoadingConnectors(true);
    try {
      // Fetch supported connectors for both INPUT and OUTPUT
      const [inputResponse, outputResponse] = await Promise.all([
        axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/supported_connectors/`,
          {
            params: {
              type: "INPUT",
            },
          }
        ),
        axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/supported_connectors/`,
          {
            params: {
              type: "OUTPUT",
            },
          }
        ),
      ]);

      // Combine and deduplicate connectors
      const inputConnectors = inputResponse.data || [];
      const outputConnectors = outputResponse.data || [];
      const allConnectors = [...inputConnectors, ...outputConnectors];

      // Remove duplicates based on id
      const uniqueConnectors = allConnectors.filter(
        (connector, index, self) =>
          index === self.findIndex((c) => c.id === connector.id)
      );

      setAvailableConnectors(uniqueConnectors);
    } catch (error) {
      setAlertDetails(
        handleException(error, "Failed to load available connectors")
      );
    } finally {
      setLoadingConnectors(false);
    }
  };

  const handleConnectorSelection = async (connector) => {
    setSelectedConnector(connector);
    setIsLoading(true);

    try {
      // Get the spec for the selected connector
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/connector_schema/`,
        {
          params: {
            id: connector.id,
          },
        }
      );

      // Extract the json_schema from the response
      const schemaData = response.data || {};
      const jsonSchema = schemaData.json_schema || {};
      setSpec(jsonSchema);
      setCurrentStep(1);
    } catch (error) {
      setAlertDetails(
        handleException(error, "Failed to load connector specification")
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleNext = () => {
    if (currentStep === 0 && selectedConnector) {
      handleConnectorSelection(selectedConnector);
    }
  };

  const handleBack = () => {
    if (currentStep === 1) {
      setCurrentStep(0);
    }
  };

  const handleSubmit = async (connectorFormData) => {
    setIsLoading(true);
    try {
      const payload = {
        connector_id: selectedConnector.id,
        connector_name:
          connectorFormData.connector_name ||
          `${selectedConnector.name} Connector`,
        connector_type: selectedConnector.connector_mode || "UNKNOWN",
        connector_metadata: connectorFormData,
        shared_users: [],
      };

      let response;
      if (connectorData?.id) {
        // Update existing connector
        response = await axiosPrivate.patch(
          `/api/v1/unstract/${sessionDetails?.orgId}/connector/${connectorData.id}/`,
          payload,
          {
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
            },
          }
        );
      } else {
        // Create new connector
        response = await axiosPrivate.post(
          `/api/v1/unstract/${sessionDetails?.orgId}/connector/`,
          payload,
          {
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
            },
          }
        );
      }

      onSave(response.data);
    } catch (error) {
      setAlertDetails(
        handleException(
          error,
          connectorData
            ? "Failed to update connector"
            : "Failed to create connector"
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const steps = [
    {
      title: "Select Connector",
      content: (
        <div style={{ padding: "20px 0" }}>
          <Title level={4}>Choose a Connector</Title>
          <ConnectorListModal
            connectors={availableConnectors}
            onSelectConnector={handleConnectorSelection}
            selectedConnectorId={selectedConnector?.id}
            loading={loadingConnectors}
          />
        </div>
      ),
    },
    {
      title: "Configure",
      content: (
        <div style={{ padding: "20px 0" }}>
          {selectedConnector && spec && (
            <ConfigureDs
              spec={spec}
              formData={formData}
              setFormData={setFormData}
              selectedSourceId={selectedConnector.id}
              isLoading={isLoading}
              addNewItem={handleSubmit}
              type="connector"
              sourceType={selectedConnector.connector_mode || "UNKNOWN"}
              selectedSourceName={selectedConnector.name}
              connType="connector"
              editItemId={connectorData?.id}
              handleUpdate={handleSubmit}
              connDetails={connectorData}
              metadata={connectorData?.connector_metadata}
            />
          )}
        </div>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      title={connectorData ? "Edit Connector" : "Create Connector"}
      width={1000}
      footer={null}
      maskClosable={false}
    >
      <Steps current={currentStep} items={steps} style={{ marginBottom: 24 }} />
      <div style={{ minHeight: 300 }}>{steps[currentStep].content}</div>
      <div style={{ marginTop: 24, textAlign: "right" }}>
        {currentStep > 0 && (
          <Button style={{ marginRight: 8 }} onClick={handleBack}>
            Back
          </Button>
        )}
        {currentStep === 0 && (
          <Button
            type="primary"
            onClick={handleNext}
            disabled={!selectedConnector}
            loading={isLoading}
          >
            Next
          </Button>
        )}
        {currentStep === 1 && (
          <>
            <Button onClick={onCancel} style={{ marginRight: 8 }}>
              Cancel
            </Button>
            <Button
              type="primary"
              onClick={() => handleSubmit(formData)}
              loading={isLoading}
            >
              {connectorData ? "Update" : "Create"} Connector
            </Button>
          </>
        )}
      </div>
    </Modal>
  );
}

AddConnectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
  connectorData: PropTypes.object,
};

export { AddConnectorModal };
