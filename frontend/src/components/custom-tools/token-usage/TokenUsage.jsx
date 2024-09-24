import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useTokenUsageStore } from "../../../store/token-usage-store";
import { formatNumberWithCommas } from "../../../helpers/GetStaticData";

/**
 * TokenUsage component displays token usage details in a tag with a tooltip.
 *
 * @param {string} tokenUsageId - The token usage ID to fetch token usage for.
 * @return {JSX.Element} - The TokenUsage component.
 */
function TokenUsage({ tokenUsageId, isLoading }) {
  const [tokens, setTokens] = useState({});
  const { tokenUsage } = useTokenUsageStore();

  useEffect(() => {
    // Check if the token usage for the given tokenUsageId is available
    if (tokenUsage[tokenUsageId] === undefined) {
      setTokens({}); // Reset tokens state if token usage is not available
      return;
    }

    setTokens(tokenUsage[tokenUsageId]); // Update tokens state with the token usage data for the given tokenUsageId
  }, [tokenUsage, tokenUsageId]);

  // If no tokens data is available, render nothing
  if (!tokens || !Object.keys(tokens)?.length || isLoading) {
    return "NA";
  }

  return formatNumberWithCommas(tokens?.total_tokens);
}

TokenUsage.propTypes = {
  tokenUsageId: PropTypes.string.isRequired,
  isLoading: PropTypes.bool,
};

export { TokenUsage };
