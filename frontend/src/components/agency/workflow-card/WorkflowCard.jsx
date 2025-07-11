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
  return (
    <div className="workflow-card">
      <div className="workflow-card-header">
        <div className="workflow-card-number">{number}</div>
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
