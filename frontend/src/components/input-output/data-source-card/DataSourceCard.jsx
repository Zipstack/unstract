import { Card, Image, Typography } from "antd";
import PropTypes from "prop-types";

import "./DataSourceCard.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

function DataSourceCard({ srcDetails, setSelectedSourceId, type }) {
  const { posthogEventText, setPostHogCustomEvent } = usePostHogEvents();

  const handleSelectSource = () => {
    if (srcDetails?.isDisabled) {
      return;
    }

    if (posthogEventText[type]) {
      setPostHogCustomEvent(posthogEventText[type], {
        info: `User selected ${srcDetails?.name}`,
      });
    }

    setSelectedSourceId(srcDetails?.id);
  };
  return (
    <Card
      hoverable={!srcDetails?.isDisabled}
      size="small"
      type="inner"
      bordered={true}
      className={`ds-card ${srcDetails?.isDisabled ? "disabled" : ""}`}
      onClick={handleSelectSource}
    >
      <div className="cover-container">
        {srcDetails?.isDisabled && (
          <div className="disabled-overlay">
            <Typography.Text strong>Coming Soon</Typography.Text>
          </div>
        )}
        <div className="cover-img">
          <Image
            src={srcDetails?.icon}
            width="80%"
            height="auto"
            preview={false}
          />
        </div>
        <div className="ds-card-name display-flex-center">
          <Typography>{srcDetails?.name}</Typography>
        </div>
      </div>
    </Card>
  );
}

DataSourceCard.propTypes = {
  srcDetails: PropTypes.object.isRequired,
  setSelectedSourceId: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
};

export { DataSourceCard };
