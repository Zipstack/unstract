import { Typography } from "antd";
import PropTypes from "prop-types";
import React from "react";

function TextViewer({ text }) {
  return (
    <div className="text-viewer-layout">
      <Typography.Paragraph>
        {text.split("\n").map((line) => (
          <React.Fragment key={line?.slice(0, 10)}>
            {line}
            <br />
          </React.Fragment>
        ))}
      </Typography.Paragraph>
    </div>
  );
}

TextViewer.propTypes = {
  text: PropTypes.string,
};

export { TextViewer };
