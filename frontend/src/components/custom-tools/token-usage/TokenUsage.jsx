import { Tag, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

/**
 * TokenUsage component displays token usage details in a tag with a tooltip.
 *
 * @param {Object} tokenUsage - An object containing token usage details.
 * @param {string} docId - The document ID to fetch token usage for.
 * @return {JSX.Element} - The TokenUsage component.
 */
function TokenUsage({ tokenUsage, docId }) {
  const [tokens, setTokens] = useState({});

  useEffect(() => {
    // Check if the token usage for the given docId is available
    if (tokenUsage[docId] === undefined) {
      setTokens({}); // Reset tokens state if token usage is not available
      return;
    }

    setTokens(tokenUsage[docId]); // Update tokens state with the token usage data for the given docId
  }, [tokenUsage, docId]);

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
  tokenUsage: PropTypes.object.isRequired,
  docId: PropTypes.string.isRequired,
};

export { TokenUsage };
