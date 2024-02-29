import PropTypes from "prop-types";
import { PlaceholderImg } from "../../assets";
import { Typography } from "antd";
import "./Placeholder.css";

function Placeholder({ text, subText }) {
  return (
    <div className="content-center-body">
      <div className="content-center-body-2">
        <div>
          <PlaceholderImg />
        </div>
        <div>
          <Typography.Text>{text}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">{subText}</Typography.Text>
        </div>
      </div>
    </div>
  );
}

Placeholder.propTypes = {
  text: PropTypes.string.isRequired,
  subText: PropTypes.string.isRequired,
};

export { Placeholder };
