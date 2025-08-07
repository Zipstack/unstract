import { CheckOutlined } from "@ant-design/icons";
import { Flex, Typography, Image } from "antd";
import PropTypes from "prop-types";

import { DsSettingsCard } from "../ds-settings-card/DsSettingsCard";
import "./WorkflowCard.css";

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
  // Check if step is completed (number starts with ✓ or number is a specific completed indicator)
  const isCompleted = typeof number === "string" && number.startsWith("✓");

  // Check if showing connector type instead of number
  const isConnectorType =
    typeof number === "string" &&
    ["FILESYSTEM", "DATABASE", "MANUALREVIEW", "APPDEPLOYMENT"].includes(
      number
    );

  // Determine the step number for fallback
  const stepNumber = title.includes("Source") ? "1" : "2";

  return (
    <div className="workflow-card">
      <div className="workflow-card-header">
        <div
          className={`workflow-card-number ${
            isCompleted || isConnectorType ? "completed" : ""
          }`}
        >
          {isCompleted ? (
            <CheckOutlined />
          ) : isConnectorType &&
            connectorIcon &&
            (number === "FILESYSTEM" || number === "DATABASE") ? (
            <Image
              src={connectorIcon}
              height={20}
              width={20}
              preview={false}
              className="connector-icon"
            />
          ) : isConnectorType ? (
            <span className="connector-type-badge">
              {number === "FILESYSTEM" || number === "DATABASE"
                ? stepNumber
                : number === "MANUALREVIEW"
                ? "MR"
                : number === "APPDEPLOYMENT"
                ? "AD"
                : number}
            </span>
          ) : (
            number
          )}
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
