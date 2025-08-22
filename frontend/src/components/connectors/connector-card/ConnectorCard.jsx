import { Card, Image, Typography } from "antd";
import PropTypes from "prop-types";

import "../../input-output/data-source-card/DataSourceCard.css";
import "./ConnectorCard.css";

function ConnectorCard({ connector, onSelect, isSelected = false }) {
  const handleSelect = () => {
    if (connector?.isDisabled) {
      return;
    }
    onSelect(connector);
  };

  return (
    <Card
      hoverable={!connector?.isDisabled}
      size="small"
      type="inner"
      bordered={true}
      className={`ds-card connector-card ${
        connector?.isDisabled ? "disabled" : ""
      } ${isSelected ? "selected" : ""}`}
      onClick={handleSelect}
    >
      <div className="cover-container">
        {connector?.isDisabled && (
          <div className="disabled-overlay">
            <Typography.Text strong>Coming Soon</Typography.Text>
          </div>
        )}
        <div className="cover-img">
          <Image
            src={connector?.icon}
            width="80%"
            height="auto"
            preview={false}
            fallback="/api/static/default-connector-icon.svg" // Fallback icon
          />
        </div>
        <div className="ds-card-name display-flex-center">
          <Typography.Text ellipsis={{ tooltip: connector?.name }}>
            {connector?.name}
          </Typography.Text>
        </div>
      </div>
    </Card>
  );
}

ConnectorCard.propTypes = {
  connector: PropTypes.shape({
    id: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    icon: PropTypes.string,
    isDisabled: PropTypes.bool,
    connector_mode: PropTypes.string,
  }).isRequired,
  onSelect: PropTypes.func.isRequired,
  isSelected: PropTypes.bool,
};

export { ConnectorCard };
