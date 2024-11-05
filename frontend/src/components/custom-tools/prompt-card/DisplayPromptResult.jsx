import { Spin, Typography } from "antd";
import PropTypes from "prop-types";
import { InfoCircleFilled } from "@ant-design/icons";

import {
  displayPromptResult,
  generateApiRunStatusId,
  PROMPT_RUN_API_STATUSES,
} from "../../../helpers/GetStaticData";
import "./PromptCard.css";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useEffect, useState } from "react";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function DisplayPromptResult({ output, profileId, docId, promptRunStatus }) {
  const [isLoading, setIsLoading] = useState(false);
  const { singlePassExtractMode, isSinglePassExtractLoading } =
    useCustomToolStore();

  useEffect(() => {
    if (singlePassExtractMode && isSinglePassExtractLoading) {
      setIsLoading(true);
      return;
    }

    const key = generateApiRunStatusId(docId, profileId);
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
  profileId: PropTypes.string,
  docId: PropTypes.string,
  promptRunStatus: PropTypes.object,
};

export { DisplayPromptResult };
