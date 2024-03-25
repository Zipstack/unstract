import { Tag, Tooltip } from "antd";
import PropTypes from "prop-types";

function TokenCount({ tokenCount }) {
  if (!tokenCount || !Object.keys(tokenCount)?.length) {
    return <></>;
  }

  return (
    <Tooltip title="Prompt Token Count | Completion Token Count | Total Token Count">
      <Tag color="#2db7f5">{`${tokenCount?.prompt_token_count} | ${tokenCount?.completion_token_count} | ${tokenCount?.total_token_count}`}</Tag>
    </Tooltip>
  );
}

TokenCount.propTypes = {
  tokenCount: PropTypes.object,
};

export { TokenCount };
