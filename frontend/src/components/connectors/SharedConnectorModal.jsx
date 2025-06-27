import { useEffect, useState } from "react";
import {
  Modal,
  Row,
  Col,
  Select,
  message,
  Typography,
  Button,
  Image,
} from "antd";
import PropTypes from "prop-types";

import { ConfigureDs } from "../input-output/configure-ds/ConfigureDs";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";
import { getMenuItem } from "../../helpers/GetStaticData";

// Helper function to get connector icon based on connector ID
const getConnectorIcon = (connectorId) => {
  if (!connectorId) return null;

  const connectorIconMap = {
    // S3/MinIO variants
    minio: "/icons/connector-icons/S3.png",
    s3: "/icons/connector-icons/S3.png",
    // Database connectors
    postgres: "/icons/connector-icons/Postgresql.png",
    postgresql: "/icons/connector-icons/Postgresql.png",
    mysql: "/icons/connector-icons/MySql.png",
    mariadb: "/icons/connector-icons/MariaDB.png",
    mssql: "/icons/connector-icons/MSSQL.png",
    oracle: "/icons/connector-icons/Oracle.png",
    redis: "/icons/connector-icons/Redis.png",
    bigquery: "/icons/connector-icons/Bigquery.png",
    snowflake: "/icons/connector-icons/Snowflake.png",
    redshift: "/icons/connector-icons/Redshift.png",
    // Cloud storage
    dropbox: "/icons/connector-icons/Dropbox.png",
    google_drive: "/icons/connector-icons/Google%20Drive.png",
    google_cloud_storage: "/icons/connector-icons/google_cloud_storage.png",
    azure_blob_storage: "/icons/connector-icons/azure_blob_storage.png",
    box: "/icons/connector-icons/Box.png",
    // File transfer
    sftp: "/icons/connector-icons/SFTP.png",
    http: "/icons/connector-icons/HTTP.svg",
    // Unstract specific
    unstract_storage: "/icons/connector-icons/Unstract%20Storage.png",
  };

  // Convert connectorId to lowercase for matching
  const idLower = connectorId.toLowerCase();

  // Check for exact matches first
  for (const [key, iconPath] of Object.entries(connectorIconMap)) {
    if (idLower.includes(key)) {
      return iconPath;
    }
  }

  // Default fallback - no icon
  return null;
};

function SharedConnectorModal({
  open,
  onCancel,
  onSave,
  connectorData = null, // null for create, object for edit
}) {
  const [selectedConnectorId, setSelectedConnectorId] = useState("");
  const [selectedConnectorName, setSelectedConnectorName] = useState("");
  const [connectorSpec, setConnectorSpec] = useState(null);
  const [connectorMetadata, setConnectorMetadata] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [availableConnectors, setAvailableConnectors] = useState([]);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      loadAvailableConnectors();
      if (connectorData) {
        // Editing existing connector
        setSelectedConnectorId(connectorData.connector_id);
        setSelectedConnectorName(connectorData.connector_name);
        setConnectorMetadata(connectorData.connector_metadata || {});
        loadConnectorSpec(connectorData.connector_id);
      } else {
        // Creating new connector
        resetForm();
      }
    } else {
      resetForm();
    }
  }, [open, connectorData]);

  const resetForm = () => {
    setSelectedConnectorId("");
    setSelectedConnectorName("");
    setConnectorSpec(null);
    setConnectorMetadata({});
    setAvailableConnectors([]);
  };

  const loadAvailableConnectors = async () => {
    setIsLoading(true);
    try {
      // Load both INPUT and OUTPUT connectors
      const [inputResponse, outputResponse] = await Promise.all([
        axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/supported_connectors/?type=INPUT`
        ),
        axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/supported_connectors/?type=OUTPUT`
        ),
      ]);

      const inputConnectors = inputResponse.data || [];
      const outputConnectors = outputResponse.data || [];
      const allConnectors = [...inputConnectors, ...outputConnectors];

      // Remove duplicates based on id
      const uniqueConnectors = allConnectors.filter(
        (connector, index, self) =>
          index === self.findIndex((c) => c.id === connector.id)
      );

      // Format connectors for ListOfConnectors component
      const formattedConnectors = uniqueConnectors.map((connector) => {
        const iconPath = getConnectorIcon(connector.id);
        const icon = iconPath ? (
          <Image
            src={iconPath}
            height={16}
            width={16}
            preview={false}
            style={{
              flexShrink: 0,
              display: "block",
            }}
          />
        ) : null;

        return getMenuItem(
          connector.name,
          connector.id,
          icon,
          undefined,
          undefined,
          false // Not disabled
        );
      });

      setAvailableConnectors(formattedConnectors);
    } catch (error) {
      console.error("Error loading available connectors:", error);
      message.error("Failed to load connector types");
    } finally {
      setIsLoading(false);
    }
  };

  const loadConnectorSpec = async (connectorId) => {
    if (!connectorId) return;

    setIsLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/connector_schema/?id=${connectorId}`
      );
      // Extract just the json_schema portion for the form
      setConnectorSpec(response.data?.json_schema || {});
    } catch (error) {
      console.error("Error loading connector spec:", error);
      message.error("Failed to load connector configuration");
    } finally {
      setIsLoading(false);
    }
  };

  const handleConnectorSelect = (connectorId, connectorName) => {
    setSelectedConnectorId(connectorId);
    setSelectedConnectorName(connectorName);
    setConnectorMetadata({});
    loadConnectorSpec(connectorId);
  };

  const handleSave = async () => {
    if (!selectedConnectorId) {
      message.error("Please select a connector type");
      return;
    }

    // Extract the connector name from form data
    const connectorName =
      connectorMetadata?.connectorName || selectedConnectorName;
    const cleanMetadata = { ...connectorMetadata };
    delete cleanMetadata.connectorName;

    setIsLoading(true);
    try {
      const payload = {
        connector_name: connectorName,
        connector_id: selectedConnectorId,
        connector_metadata: cleanMetadata,
        connector_type: "INPUT", // Default to INPUT for now
        is_shared: true,
      };

      if (connectorData) {
        // Update existing connector
        await axiosPrivate.put(
          `/api/v1/unstract/${sessionDetails?.orgId}/shared-connectors/${connectorData.id}/`,
          payload,
          {
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
            },
          }
        );
        message.success("Connector updated successfully");
      } else {
        // Create new connector
        await axiosPrivate.post(
          `/api/v1/unstract/${sessionDetails?.orgId}/shared-connectors/`,
          payload,
          {
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
            },
          }
        );
        message.success("Connector created successfully");
      }

      onSave();
    } catch (error) {
      console.error("Error saving connector:", error);
      const errorMsg =
        error.response?.data?.error || "Failed to save connector";
      message.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      title={connectorData ? "Edit Connector" : "Create Connector"}
      open={open}
      onCancel={onCancel}
      width={1000}
      footer={null}
      destroyOnClose
    >
      <div style={{ padding: "24px" }}>
        <Row gutter={24}>
          <Col span={24} style={{ marginBottom: "16px" }}>
            <Typography.Title
              level={4}
              style={{ margin: 0, marginBottom: "8px" }}
            >
              Select Connector Type
            </Typography.Title>
            <Select
              style={{ width: "100%" }}
              placeholder="Choose a connector type"
              value={selectedConnectorId || undefined}
              onChange={(value) => {
                const connector = availableConnectors.find(
                  (c) => c.key === value
                );
                if (connector) {
                  handleConnectorSelect(value, connector.label);
                }
              }}
              options={availableConnectors.map((connector) => ({
                value: connector.key,
                label: (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      lineHeight: "16px",
                    }}
                  >
                    {connector.icon}
                    <span style={{ lineHeight: "16px" }}>
                      {connector.label}
                    </span>
                  </div>
                ),
              }))}
              size="large"
            />
          </Col>
          {selectedConnectorId && (
            <Col span={24}>
              <div style={{ position: "relative" }}>
                <ConfigureDs
                  spec={connectorSpec || {}}
                  formData={connectorMetadata || {}}
                  setFormData={(data) => setConnectorMetadata(data)}
                  setOpen={onCancel}
                  oAuthProvider=""
                  selectedSourceId={selectedConnectorId}
                  isLoading={isLoading}
                  addNewItem={false}
                  type={connectorData?.connector_type || "INPUT"}
                  editItemId={connectorData?.id || null}
                  sourceType="connectors"
                  handleUpdate={() => {}}
                  connDetails={connectorData || {}}
                  metadata={connectorMetadata || {}}
                  selectedSourceName={selectedConnectorName}
                  connType="FILESYSTEM"
                  formDataConfig={{}}
                />
                {/* Hide ConfigureDs submit button */}
                <style
                  dangerouslySetInnerHTML={{
                    __html: `
                    .config-col2 {
                      display: none !important;
                    }
                  `,
                  }}
                />
              </div>
              {/* Custom submit button */}
              <div style={{ marginTop: "16px", textAlign: "right" }}>
                <Button
                  type="primary"
                  onClick={handleSave}
                  disabled={isLoading}
                  loading={isLoading}
                  style={{ marginRight: "8px" }}
                >
                  {isLoading ? "Saving..." : "Save Connector"}
                </Button>
              </div>
            </Col>
          )}
        </Row>
      </div>
    </Modal>
  );
}

SharedConnectorModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
  connectorData: PropTypes.object,
};

export { SharedConnectorModal };
