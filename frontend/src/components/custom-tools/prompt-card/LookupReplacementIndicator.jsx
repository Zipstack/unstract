import { SwapOutlined } from "@ant-design/icons";
import { Button, Popover, Typography } from "antd";
import PropTypes from "prop-types";

import "./LookupReplacementIndicator.css";

const { Text } = Typography;

function LookupReplacementIndicator({ lookupReplacement }) {
  if (!lookupReplacement) {
    return null;
  }

  const { original_value: originalValue, enriched_value: enrichedValue } =
    lookupReplacement;

  const content = (
    <div className="lookup-replacement-content">
      <div className="lookup-replacement-header">
        <SwapOutlined className="lookup-replacement-icon" />
        <Text strong>Look-up Replacement</Text>
      </div>
      <div className="lookup-replacement-details">
        <div className="lookup-replacement-row">
          <Text type="secondary" className="lookup-replacement-label">
            Original:
          </Text>
          <Text className="lookup-replacement-value original">
            {originalValue || "(empty)"}
          </Text>
        </div>
        <div className="lookup-replacement-arrow">
          <SwapOutlined rotate={90} />
        </div>
        <div className="lookup-replacement-row">
          <Text type="secondary" className="lookup-replacement-label">
            Replaced:
          </Text>
          <Text className="lookup-replacement-value enriched">
            {enrichedValue || "(empty)"}
          </Text>
        </div>
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      title={null}
      trigger="hover"
      placement="top"
      overlayClassName="lookup-replacement-popover"
    >
      <Button
        size="small"
        type="text"
        className="prompt-card-action-button lookup-indicator-btn"
      >
        <SwapOutlined className="prompt-card-actions-head lookup-indicator-icon" />
      </Button>
    </Popover>
  );
}

LookupReplacementIndicator.propTypes = {
  lookupReplacement: PropTypes.shape({
    original_value: PropTypes.oneOfType([PropTypes.string, PropTypes.any]),
    enriched_value: PropTypes.oneOfType([PropTypes.string, PropTypes.any]),
    field_name: PropTypes.string,
  }),
};

export { LookupReplacementIndicator };
