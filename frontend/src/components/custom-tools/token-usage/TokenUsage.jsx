import { Tag, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useTokenUsageStore } from "../../../store/token-usage-store";

/**
 * TokenUsage component displays token usage details in a tag with a tooltip.
 *
 * @param {string} tokenUsageId - The token usage ID to fetch token usage for.
 * @return {JSX.Element} - The TokenUsage component.
 */
function TokenUsage({ tokenUsageId }) {
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
  if (!tokens || !Object.keys(tokens)?.length) {
    return <></>;
  }

  return (
    <Tooltip title="Total Token Count">
      <Tag color="#2db7f5">{`Tokens: ${tokens?.total_tokens}`}</Tag>
    </Tooltip>
  );
}

TokenUsage.propTypes = {
  tokenUsageId: PropTypes.string.isRequired,
};

export { TokenUsage };
