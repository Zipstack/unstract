import { Lock } from "lucide-react";
import PropTypes from "prop-types";

import "./ReadOnlyNotice.css";

/** Tells a shared user, up front, that this workflow is not theirs to change. */
function ReadOnlyNotice({
  message = "Shared with you — view only. Only the owner can change this.",
}) {
  return (
    <div className="read-only-notice">
      <Lock className="read-only-notice__icon" size={14} />
      <span>{message}</span>
    </div>
  );
}

ReadOnlyNotice.propTypes = {
  message: PropTypes.string,
};

export { ReadOnlyNotice };
