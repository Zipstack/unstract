import { ArrowsAltOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";

import { PromptOutputsModal } from "./PromptOutputsModal";

function PromptOutputExpandBtn({
  promptId,
  llmProfiles,
  enforceType,
  displayLlmProfile,
  promptOutputs,
  promptRunStatus,
  tableSettings,
  openExpandModal,
  setOpenExpandModal,
}) {
  return (
    <>
      <Tooltip title="Expand">
        <Button
          size="small"
          type="text"
          className="prompt-card-action-button"
          onClick={() => setOpenExpandModal(true)}
        >
          <ArrowsAltOutlined className="prompt-card-actions-head" />
        </Button>
      </Tooltip>
      <PromptOutputsModal
        open={openExpandModal}
        setOpen={setOpenExpandModal}
        promptId={promptId}
        llmProfiles={llmProfiles}
        enforceType={enforceType}
        tableSettings={tableSettings}
        displayLlmProfile={displayLlmProfile}
        promptOutputs={promptOutputs}
        promptRunStatus={promptRunStatus}
      />
    </>
  );
}

PromptOutputExpandBtn.propTypes = {
  promptId: PropTypes.string.isRequired,
  llmProfiles: PropTypes.array.isRequired,
  enforceType: PropTypes.string,
  tableSettings: PropTypes.object,
  displayLlmProfile: PropTypes.bool.isRequired,
  promptOutputs: PropTypes.object.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
  openExpandModal: PropTypes.bool.isRequired,
  setOpenExpandModal: PropTypes.func.isRequired,
};

export { PromptOutputExpandBtn };
