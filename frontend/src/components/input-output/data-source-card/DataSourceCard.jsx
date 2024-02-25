import { Card, Image, Typography } from "antd";
import PropTypes from "prop-types";

import "./DataSourceCard.css";

function DataSourceCard({ srcDetails, setSelectedSourceId }) {
  return (
    <Card
      hoverable
      size="small"
      type="inner"
      bordered={true}
      className="ds-card"
      cover={
        <div className="cover-img">
          <Image
            src={srcDetails?.icon}
            width="100%"
            height="auto"
            preview={false}
          />
        </div>
      }
      onClick={() => setSelectedSourceId(srcDetails?.id)}
    >
      <div className="ds-card-name display-flex-center">
        <Typography>{srcDetails?.name}</Typography>
      </div>
    </Card>
  );
}

DataSourceCard.propTypes = {
  srcDetails: PropTypes.object.isRequired,
  setSelectedSourceId: PropTypes.func.isRequired,
};

export { DataSourceCard };
