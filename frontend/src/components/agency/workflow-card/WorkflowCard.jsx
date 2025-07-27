import { CheckOutlined } from "@ant-design/icons";
import { Flex, Typography } from "antd";
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
}) {
  // Check if step is completed (number starts with ✓ or number is a specific completed indicator)
  const isCompleted = typeof number === "string" && number.startsWith("✓");

  return (
    <div className="workflow-card">
      <div className="workflow-card-header">
        <div
          className={`workflow-card-number ${isCompleted ? "completed" : ""}`}
        >
          {isCompleted ? <CheckOutlined /> : number}
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
};

export { WorkflowCard };
