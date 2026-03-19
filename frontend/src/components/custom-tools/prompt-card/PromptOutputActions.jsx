import { PlayCircleFilled, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";

import { useCustomToolStore } from "../../../store/custom-tool-store";

function PromptOutputActions({
  isNotSingleLlmProfile,
  handleRun,
  profileId,
  isRunLoading,
}) {
  const { selectedDoc, isPublicSource } = useCustomToolStore();

  if (isNotSingleLlmProfile) {
    return <></>;
  }

  return (
    <>
      <Tooltip title="Run">
        <Button
          size="small"
          type="text"
          className="prompt-card-action-button"
          onClick={() => handleRun(profileId, false)}
          disabled={
            isRunLoading[`${selectedDoc?.document_id}_${profileId}`] ||
            isPublicSource
          }
        >
          <PlayCircleOutlined className="prompt-card-actions-head" />
        </Button>
      </Tooltip>
      <Tooltip title="Run All">
        <Button
          size="small"
          type="text"
          className="prompt-card-action-button"
          onClick={() => handleRun(profileId, true)}
          disabled={
            isRunLoading[`${selectedDoc?.document_id}_${profileId}`] ||
            isPublicSource
          }
        >
          <PlayCircleFilled className="prompt-card-actions-head" />
        </Button>
      </Tooltip>
    </>
  );
}

PromptOutputActions.propTypes = {
  isNotSingleLlmProfile: PropTypes.bool.isRequired,
  handleRun: PropTypes.func.isRequired,
  profileId: PropTypes.string.isRequired,
  isRunLoading: PropTypes.bool.isRequired,
};

export { PromptOutputActions };
