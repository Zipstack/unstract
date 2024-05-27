import { Image } from "antd";
import emojiRegex from "emoji-regex";
import PropTypes from "prop-types";

import "./ToolIcon.css";

function ToolIcon({ iconSrc, showBorder }) {
  const emojiregex = emojiRegex();
  const isSVG =
    iconSrc && typeof iconSrc === "string" && iconSrc.includes("<svg");

  if (isSVG) {
    // If it's an SVG, render it as an image
    const uri = `data:image/svg+xml,${encodeURIComponent(iconSrc)}`;
    return (
      <div
        className={`display-flex-center ${
          showBorder ? "tool-icon-border" : ""
        }`}
      >
        <Image src={uri} preview={false} height={30} width={30} />
      </div>
    );
  } else if (typeof iconSrc === "string" && emojiregex.test(iconSrc)) {
    // If it's a string, render it using Typography
    return (
      <div
        className={`display-flex-center ${
          showBorder ? "tool-icon-border" : ""
        }`}
      >
        {iconSrc}
      </div>
    );
  } else {
    // Handle other cases if needed
    return (
      <div
        className={`display-flex-center ${
          showBorder ? "tool-icon-border" : ""
        }`}
      >
        {"🧰"}
      </div>
    );
  }
}

ToolIcon.propTypes = {
  iconSrc: PropTypes.string,
  showBorder: PropTypes.bool,
};

export { ToolIcon };
