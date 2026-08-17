import { Image } from "antd";
import PropTypes from "prop-types";

import { isImageUrl } from "../../../helpers/GetStaticData";

// Adapter icons are image paths; unresolved ones fall back to an emoji.
function ProfileIcon({ icon }) {
  if (!isImageUrl(icon)) {
    return <span className="prompt-card-llm-icon">{icon || "⚠️"}</span>;
  }
  return (
    <Image
      src={icon}
      width={15}
      height={15}
      preview={false}
      className="prompt-card-llm-icon"
    />
  );
}

ProfileIcon.propTypes = {
  icon: PropTypes.string,
};

export { ProfileIcon };
