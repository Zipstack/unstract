import { useState, useEffect } from "react";
import {
  Button,
  Typography,
  Space,
  Tag,
  Empty,
  message,
  List,
  Popconfirm,
  Avatar,
  Flex,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UserOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";

import { useAxiosPrivate } from "../hooks/useAxiosPrivate";
import { useSessionStore } from "../store/session-store";
import { SharedConnectorModal } from "../components/connectors/SharedConnectorModal";
import "../components/widgets/list-view/ListView.css";

function ConnectorsPage() {
  const [connectors, setConnectors] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConnector, setEditingConnector] = useState(null);
  const [filterType, setFilterType] = useState("ALL"); // ALL, INPUT, OUTPUT

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchConnectors();
  }, []);

  const fetchConnectors = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/shared-connectors/`
      );
      setConnectors(response.data?.results || response.data || []);
    } catch (error) {
      console.error("Failed to fetch connectors:", error);
      message.error("Failed to load connectors");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateConnector = () => {
    setEditingConnector(null);
    setModalVisible(true);
  };

  const handleEditConnector = (event, connector) => {
    event.stopPropagation();
    setEditingConnector(connector);
    setModalVisible(true);
  };

  const handleDeleteConnector = async (event, connector) => {
    event.stopPropagation();
    try {
      await axiosPrivate.delete(
        `/api/v1/unstract/${sessionDetails?.orgId}/shared-connectors/${connector.id}/`
      );
      message.success("Connector deleted successfully");
      fetchConnectors();
    } catch (error) {
      console.error("Failed to delete connector:", error);
      message.error("Failed to delete connector");
    }
  };

  const handleModalClose = () => {
    setModalVisible(false);
    setEditingConnector(null);
  };

  const handleConnectorSaved = () => {
    setModalVisible(false);
    setEditingConnector(null);
    fetchConnectors();
    message.success(
      editingConnector
        ? "Connector updated successfully"
        : "Connector created successfully"
    );
  };

  const getConnectorIcon = (connectorType, connectorMode, connectorId) => {
    // Helper function to get connector icon path based on connector ID
    const getConnectorIconPath = (connectorId) => {
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
        azure_cloud_storage: "/icons/connector-icons/azure_blob_storage.png",
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

      return null;
    };

    // Try to get specific connector icon first
    const iconPath = getConnectorIconPath(connectorId);
    if (iconPath) {
      return iconPath;
    }

    return null;
  };

  const getConnectorTypeName = (connectorId) => {
    // Extract connector name from ID (e.g., "minio|uuid" -> "S3/MinIO")
    if (connectorId.includes("minio")) return "S3/MinIO";
    if (connectorId.includes("dropbox")) return "Dropbox";
    if (connectorId.includes("google_drive")) return "Google Drive";
    if (connectorId.includes("azure")) return "Azure Storage";
    if (connectorId.includes("postgres")) return "PostgreSQL";
    if (connectorId.includes("mysql")) return "MySQL";
    if (connectorId.includes("bigquery")) return "BigQuery";
    if (connectorId.includes("snowflake")) return "Snowflake";
    if (connectorId.includes("redshift")) return "Redshift";

    // Fallback - extract the part before the pipe
    const parts = connectorId.split("|");
    return parts[0]?.toUpperCase() || "Unknown";
  };

  const getFilteredConnectors = () => {
    if (filterType === "ALL") return connectors;
    return connectors.filter(
      (connector) => connector.connector_type === filterType
    );
  };

  const filteredConnectors = getFilteredConnectors();

  const renderConnectorTitle = (connector) => {
    const iconPath = getConnectorIcon(
      connector.connector_type,
      connector.connector_mode,
      connector.connector_id
    );

    return (
      <Flex
        gap={20}
        align="center"
        justify="space-between"
        style={{ width: "100%" }}
      >
        <div style={{ display: "flex", width: "80%" }}>
          <div style={{ width: "50%", paddingRight: "12px" }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              {iconPath && (
                <img
                  src={iconPath}
                  alt="connector icon"
                  style={{ width: 90, height: 90, marginRight: 12 }}
                />
              )}
              <Typography.Text style={{ fontSize: "16px" }}>
                {connector.connector_name}
              </Typography.Text>
            </div>
          </div>
          <div
            style={{
              alignItems: "center",
              display: "flex",
              justifyContent: "center",
            }}
          >
            <Avatar
              size={20}
              style={{ marginRight: "8px" }}
              icon={<UserOutlined />}
            />
            <Typography.Text
              disabled
              style={{ margin: "0 5px", fontWeight: 500 }}
            >
              Owned By:
            </Typography.Text>
            <Typography.Text>
              {connector?.created_by_email
                ? connector?.created_by_email === sessionDetails.email
                  ? "Me"
                  : connector?.created_by_email
                : "-"}
            </Typography.Text>
          </div>
        </div>
        <div
          style={{ display: "flex", alignItems: "center" }}
          onClick={(event) => event.stopPropagation()}
        >
          <EditOutlined
            onClick={(event) => handleEditConnector(event, connector)}
            style={{
              fontSize: "18px",
              marginLeft: "20px",
              color: "#092c4c",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => (e.target.style.color = "#1890ff")}
            onMouseLeave={(e) => (e.target.style.color = "#092c4c")}
          />
          <Popconfirm
            title="Delete Connector"
            description={`Are you sure to delete ${connector.connector_name}?`}
            okText="Yes"
            cancelText="No"
            icon={<QuestionCircleOutlined />}
            onConfirm={(event) => handleDeleteConnector(event, connector)}
          >
            <DeleteOutlined
              style={{
                fontSize: "18px",
                marginLeft: "20px",
                color: "#092c4c",
                cursor: "pointer",
              }}
              onMouseEnter={(e) => (e.target.style.color = "#ff4d4f")}
              onMouseLeave={(e) => (e.target.style.color = "#092c4c")}
            />
          </Popconfirm>
        </div>
      </Flex>
    );
  };

  const renderDescription = (connector) => {
    return (
      <div>
        <Typography.Text type="secondary">
          {getConnectorTypeName(connector.connector_id)}
        </Typography.Text>
        <div style={{ marginTop: "8px" }}>
          <Space>
            <Tag
              color={connector.connector_type === "INPUT" ? "blue" : "green"}
            >
              {connector.connector_type}
            </Tag>
            <Tag>
              {connector.connector_mode === 1
                ? "File System"
                : connector.connector_mode === 2
                ? "Database"
                : "Unknown"}
            </Tag>
          </Space>
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: "24px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px",
          }}
        >
          <Typography
            style={{
              fontWeight: 600,
              fontSize: "18px",
              lineHeight: "24px",
            }}
          >
            Connectors
          </Typography>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateConnector}
          >
            Create Connector
          </Button>
        </div>
        <Typography.Text type="secondary">
          Manage centralized connectors for data sources and destinations. These
          connectors can be reused across multiple workflows.
        </Typography.Text>

        {/* Filter Buttons */}
        <div style={{ marginTop: "16px" }}>
          <Space>
            <Button
              type={filterType === "ALL" ? "primary" : "default"}
              onClick={() => setFilterType("ALL")}
            >
              All ({connectors.length})
            </Button>
            <Button
              type={filterType === "INPUT" ? "primary" : "default"}
              onClick={() => setFilterType("INPUT")}
            >
              Input (
              {connectors.filter((c) => c.connector_type === "INPUT").length})
            </Button>
            <Button
              type={filterType === "OUTPUT" ? "primary" : "default"}
              onClick={() => setFilterType("OUTPUT")}
            >
              Output (
              {connectors.filter((c) => c.connector_type === "OUTPUT").length})
            </Button>
          </Space>
        </div>
      </div>

      {/* List Content */}
      <div
        style={{
          width: "70%",
          minWidth: "800px",
          maxWidth: "1400px",
          padding: "0px 10px",
          margin: "0 auto",
        }}
      >
        {loading ? (
          <div style={{ textAlign: "center", padding: "50px" }}>Loading...</div>
        ) : filteredConnectors.length === 0 ? (
          <Empty
            description={
              filterType === "ALL"
                ? "No connectors configured yet"
                : `No ${filterType.toLowerCase()} connectors configured`
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreateConnector}
            >
              Create First Connector
            </Button>
          </Empty>
        ) : (
          <List
            size="large"
            dataSource={filteredConnectors}
            pagination={{
              position: "bottom",
              align: "end",
              size: "small",
            }}
            renderItem={(connector) => (
              <List.Item
                key={connector.id}
                className="cur-pointer centered"
                style={{
                  padding: "10px 0",
                  overflow: "hidden",
                  cursor: "pointer",
                }}
              >
                <List.Item.Meta
                  style={{ paddingBottom: "10px" }}
                  title={renderConnectorTitle(connector)}
                  description={renderDescription(connector)}
                />
              </List.Item>
            )}
          />
        )}
      </div>

      {modalVisible && (
        <SharedConnectorModal
          open={modalVisible}
          onCancel={handleModalClose}
          onSave={handleConnectorSaved}
          connectorData={editingConnector}
        />
      )}
    </div>
  );
}

export { ConnectorsPage };
