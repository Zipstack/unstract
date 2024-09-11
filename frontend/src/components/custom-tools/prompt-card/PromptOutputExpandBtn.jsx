import { ArrowsAltOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { PromptOutputsModal } from "./PromptOutputsModal";

function PromptOutputExpandBtn({
  llmProfiles,
  result,
  enforceType,
  displayLlmProfile,
}) {
  const [openModal, setOpenModal] = useState(false);

  return (
    <>
      <Tooltip title="Expand">
        <Button
          size="small"
          type="text"
          className="prompt-card-action-button"
          onClick={() => setOpenModal(true)}
        >
          <ArrowsAltOutlined className="prompt-card-actions-head" />
        </Button>
      </Tooltip>
      <PromptOutputsModal
        open={openModal}
        setOpen={setOpenModal}
        llmProfiles={llmProfiles}
        result={result}
        enforceType={enforceType}
        displayLlmProfile={displayLlmProfile}
      />
    </>
  );
}

PromptOutputExpandBtn.propTypes = {
  llmProfiles: PropTypes.array.isRequired,
  result: PropTypes.array.isRequired,
  enforceType: PropTypes.string.isRequired,
  displayLlmProfile: PropTypes.bool.isRequired,
};

export { PromptOutputExpandBtn };
