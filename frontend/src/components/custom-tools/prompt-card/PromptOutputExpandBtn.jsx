import { ArrowsAltOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { PromptOutputsModal } from "./PromptOutputsModal";

function PromptOutputExpandBtn({
  promptId,
  llmProfiles,
  enforceType,
  displayLlmProfile,
  promptOutputs,
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
        promptId={promptId}
        llmProfiles={llmProfiles}
        enforceType={enforceType}
        displayLlmProfile={displayLlmProfile}
        promptOutputs={promptOutputs}
      />
    </>
  );
}

PromptOutputExpandBtn.propTypes = {
  promptId: PropTypes.string.isRequired,
  llmProfiles: PropTypes.array.isRequired,
  enforceType: PropTypes.string,
  displayLlmProfile: PropTypes.bool.isRequired,
  promptOutputs: PropTypes.object.isRequired,
};

export { PromptOutputExpandBtn };
