import PropTypes from "prop-types";
import "./ContentCenterLayout.css";
import { Typography } from "antd";

function ContentCenterLayout({ children, headerText, mainText, subText }) {
  return (
    <div className="content-center-layout">
      {headerText?.length > 0 && (
        <div className="content-center-header">
          <Typography className="content-center-header-text">
            {headerText}
          </Typography>
        </div>
      )}
      <div className="content-center-body">
        <div className="content-center-body-2">
          <div className="content-center-body-3">
            <div>{children}</div>
            <div>
              <Typography.Text>{mainText}</Typography.Text>
            </div>
            <div>
              <Typography.Text type="secondary">{subText}</Typography.Text>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

ContentCenterLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
  headerText: PropTypes.string,
  mainText: PropTypes.string,
  subText: PropTypes.string,
};

export { ContentCenterLayout };
