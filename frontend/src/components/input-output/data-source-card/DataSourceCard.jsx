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

    setSelectedSourceId(srcDetails?.id);

    try {
      setPostHogCustomEvent(posthogEventText[type], {
        info: "Clicked on the adapters card",
        adapter_name: srcDetails?.name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
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
            width="50%"
            height="50%"
            preview={false}
            style={{ objectFit: "contain" }}
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
