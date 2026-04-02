import PropTypes from "prop-types";
import { memo } from "react";

const PromptRunTimer = memo(({ timer, isLoading }) => {
  if (!timer || isLoading) {
    return "Time: 0s";
  }

  return `Time: ${timer}s`;
});

PromptRunTimer.displayName = "PromptRunTimer";

PromptRunTimer.propTypes = {
  timer: PropTypes.number,
  isLoading: PropTypes.bool,
};

export { PromptRunTimer };
