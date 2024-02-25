import { Image } from "antd";
import PropTypes from "prop-types";

import "./ToolIcon.css";
import { useEffect, useState } from "react";

function ToolIcon({ iconSrc }) {
  const [svgDataUri, setSvgDataUri] = useState("");
  useEffect(() => {
    if (!iconSrc) {
      setSvgDataUri("");
      return;
    }

    const uri = `data:image/svg+xml,${encodeURIComponent(iconSrc)}`;
    setSvgDataUri(uri);
  }, [iconSrc]);
  return (
    <div className="tool-icon-border display-flex-center">
      <Image src={svgDataUri} preview={false} height={30} width={30} />
    </div>
  );
}

ToolIcon.propTypes = {
  iconSrc: PropTypes.string,
};

export { ToolIcon };
