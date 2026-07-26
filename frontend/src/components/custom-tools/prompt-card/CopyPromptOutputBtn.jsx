import { Tooltip } from "antd";
import { Copy } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/antd-button";

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
        <Copy className="prompt-card-actions-head" />
      </Button>
    </Tooltip>
  );
}

CopyPromptOutputBtn.propTypes = {
  isDisabled: PropTypes.bool.isRequired,
  copyToClipboard: PropTypes.func.isRequired,
};

export { CopyPromptOutputBtn };
