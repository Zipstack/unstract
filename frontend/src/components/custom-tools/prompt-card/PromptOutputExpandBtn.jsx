import { Move } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Tooltip } from "@/components/ui/shims/antd-overlays";

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
  testId,
}) {
  return (
    <>
      <Tooltip title="Expand">
        <Button
          data-testid={testId}
          size="small"
          type="text"
          className="prompt-card-action-button"
          onClick={() => setOpenExpandModal(true)}
        >
          <Move className="prompt-card-actions-head" />
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
  testId: PropTypes.string,
};

export { PromptOutputExpandBtn };
