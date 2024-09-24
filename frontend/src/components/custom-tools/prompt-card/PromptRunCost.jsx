import { memo } from "react";
import PropTypes from "prop-types";

import {
  formatNumberWithCommas,
  getFormattedTotalCost,
} from "../../../helpers/GetStaticData";

const PromptRunCost = memo(({ tokenUsage, isLoading }) => {
  if (!tokenUsage || isLoading) {
    return "Cost: NA";
  }

  return `Cost: $${formatNumberWithCommas(getFormattedTotalCost(tokenUsage))}`;
});

PromptRunCost.displayName = "PromptRunCost";

PromptRunCost.propTypes = {
  tokenUsage: PropTypes.object,
  isLoading: PropTypes.bool,
};

export { PromptRunCost };
