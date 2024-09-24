import { memo } from "react";
import PropTypes from "prop-types";

const PromptRunTimer = memo(({ timer, isLoading }) => {
  if (!timer?.startTime || !timer?.endTime || isLoading) {
    return "Time: 0s";
  }

  return `Time: ${Math.floor((timer?.endTime - timer?.startTime) / 1000)}s`;
});

PromptRunTimer.displayName = "PromptRunTimer";

PromptRunTimer.propTypes = {
  timer: PropTypes.object,
  isLoading: PropTypes.bool,
};

export { PromptRunTimer };
