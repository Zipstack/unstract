import { CopyOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";

function CopyPromptOutputBtn({ isDisabled, copyToClipboard }) {
  return (
    <Tooltip title="Copy prompt output">
      <Button
        size="small"
        type="text"
        className="prompt-card-action-button"
        onClick={copyToClipboard}
        disabled={isDisabled}
      >
        <CopyOutlined className="prompt-card-actions-head" />
      </Button>
    </Tooltip>
  );
}

CopyPromptOutputBtn.propTypes = {
  isDisabled: PropTypes.bool.isRequired,
  copyToClipboard: PropTypes.func.isRequired,
};

export { CopyPromptOutputBtn };
