import PropTypes from "prop-types";
import { Image } from "@/components/ui/shims/antd-leaves";

import { isImageUrl } from "../../../helpers/GetStaticData";

function ProfileIcon({ icon }) {
  if (!isImageUrl(icon)) {
    return <span className="prompt-card-llm-icon">{icon}</span>;
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
