import { Card, Image, Typography } from "antd";
import PropTypes from "prop-types";

import "./DataSourceCard.css";

function DataSourceCard({ srcDetails, setSelectedSourceId }) {
  return (
    <Card
      hoverable={!srcDetails?.isDisabled}
      size="small"
      type="inner"
      bordered={true}
      className={`ds-card ${srcDetails?.isDisabled ? "disabled" : ""}`}
      onClick={() =>
        !srcDetails?.isDisabled && setSelectedSourceId(srcDetails?.id)
      }
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
            width="100%"
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
};

export { DataSourceCard };
