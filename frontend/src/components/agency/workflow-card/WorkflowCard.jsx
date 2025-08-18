import { CheckOutlined } from "@ant-design/icons";
import { Flex, Typography, Image } from "antd";
import PropTypes from "prop-types";

import { DsSettingsCard } from "../ds-settings-card/DsSettingsCard";
import "./WorkflowCard.css";

// Constants for connector types
const CONNECTOR_TYPES = {
  FILESYSTEM: "FILESYSTEM",
  DATABASE: "DATABASE",
  MANUALREVIEW: "MANUALREVIEW",
  APPDEPLOYMENT: "APPDEPLOYMENT",
};

// Mapping for connector type abbreviations
const CONNECTOR_ABBREVIATIONS = {
  [CONNECTOR_TYPES.MANUALREVIEW]: "MR",
  [CONNECTOR_TYPES.APPDEPLOYMENT]: "AD",
};

// Helper functions to reduce complexity
const isStringType = (value) => typeof value === "string";
const isCompletedStatus = (number) =>
  isStringType(number) && number.startsWith("✓");
const isConnectorTypeStatus = (number) =>
  isStringType(number) && Object.values(CONNECTOR_TYPES).includes(number);
const isFileSystemOrDatabase = (number) =>
  number === CONNECTOR_TYPES.FILESYSTEM || number === CONNECTOR_TYPES.DATABASE;

// Render connector icon
const renderConnectorIcon = (connectorIcon) => (
  <Image
    src={connectorIcon}
    height={20}
    width={20}
    preview={false}
    className="connector-icon"
  />
);

// Render connector badge
const renderConnectorBadge = (number, stepNumber) => {
  const displayText = isFileSystemOrDatabase(number)
    ? stepNumber
    : CONNECTOR_ABBREVIATIONS[number] || number;

  return <span className="connector-type-badge">{displayText}</span>;
};

// Main function to render the number display
const renderNumberDisplay = (number, connectorIcon, stepNumber) => {
  if (isCompletedStatus(number)) {
    return <CheckOutlined />;
  }

  if (isConnectorTypeStatus(number)) {
    const hasIcon = connectorIcon && isFileSystemOrDatabase(number);
    return hasIcon
      ? renderConnectorIcon(connectorIcon)
      : renderConnectorBadge(number, stepNumber);
  }

  return number;
};

function WorkflowCard({
  number,
  title,
  description,
  type,
  endpointDetails,
  message,
  customContent,
  connectorIcon,
}) {
  const isCompleted = isCompletedStatus(number);
  const isConnectorType = isConnectorTypeStatus(number);
  const stepNumber = title.includes("Source") ? "1" : "2";
  const showCompletedStyle = isCompleted || isConnectorType;

  return (
    <div className="workflow-card">
      <div className="workflow-card-header">
        <div
          className={`workflow-card-number ${
            showCompletedStyle ? "completed" : ""
          }`}
        >
          {renderNumberDisplay(number, connectorIcon, stepNumber)}
        </div>
        <Flex vertical>
          <div className="workflow-card-info">
            <Typography.Title level={4}>{title}</Typography.Title>
            <Typography.Text type="secondary">{description}</Typography.Text>
          </div>
          <div className="workflow-card-content">
            {customContent || (
              <DsSettingsCard
                type={type}
                endpointDetails={endpointDetails}
                message={message}
              />
            )}
          </div>
        </Flex>
      </div>
    </div>
  );
}

WorkflowCard.propTypes = {
  number: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  title: PropTypes.string.isRequired,
  description: PropTypes.string.isRequired,
  type: PropTypes.string,
  endpointDetails: PropTypes.object,
  message: PropTypes.string,
  customContent: PropTypes.node,
  connectorIcon: PropTypes.string,
};

export { WorkflowCard };
