import { Spin, Typography } from "antd";
import PropTypes from "prop-types";
import { InfoCircleFilled } from "@ant-design/icons";

import {
  displayPromptResult,
  PROMPT_RUN_API_STATUSES,
} from "../../../helpers/GetStaticData";
import "./PromptCard.css";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useEffect, useState } from "react";
import usePromptOutput from "../../../hooks/usePromptOutput";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function DisplayPromptResult({ output, promptId, profileId, docId }) {
  const [isLoading, setIsLoading] = useState(false);
  const { promptRunStatus } = usePromptRunStatusStore();
  const { singlePassExtractMode, isSinglePassExtractLoading } =
    useCustomToolStore();
  const { generatePromptOutputKey } = usePromptOutput();

  useEffect(() => {
    if (singlePassExtractMode && isSinglePassExtractLoading) {
      setIsLoading(true);
      return;
    }

    const key = generatePromptOutputKey(
      promptId,
      docId,
      profileId,
      false,
      false
    );
    if (promptRunStatus?.[key] === PROMPT_RUN_API_STATUSES.RUNNING) {
      setIsLoading(true);
      return;
    }

    setIsLoading(false);
  }, [promptRunStatus, isSinglePassExtractLoading]);

  if (isLoading) {
    return <Spin indicator={<SpinnerLoader size="small" />} />;
  }

  if (output === undefined) {
    return (
      <Typography.Text className="prompt-not-ran">
        <span>
          <InfoCircleFilled className="info-circle-colored" />
        </span>{" "}
        Yet to run
      </Typography.Text>
    );
  }

  return (
    <Typography.Paragraph className="prompt-card-display-output font-size-12">
      <div>{displayPromptResult(output, true)}</div>
    </Typography.Paragraph>
  );
}

DisplayPromptResult.propTypes = {
  output: PropTypes.any,
  promptId: PropTypes.string,
  profileId: PropTypes.string,
  docId: PropTypes.string,
};

export { DisplayPromptResult };
