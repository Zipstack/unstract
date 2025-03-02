import { Spin, Typography } from "antd";
import PropTypes from "prop-types";
import { InfoCircleFilled } from "@ant-design/icons";
import { useEffect, useState } from "react";

import {
  displayPromptResult,
  generateApiRunStatusId,
  PROMPT_RUN_API_STATUSES,
} from "../../../helpers/GetStaticData";
import "./PromptCard.css";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function DisplayPromptResult({
  output,
  profileId,
  docId,
  promptRunStatus,
  handleSelectHighlight,
  highlightData,
  promptDetails,
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [parsedOutput, setParsedOutput] = useState(null);
  const { singlePassExtractMode, isSinglePassExtractLoading, details } =
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
    setParsedOutput(
      displayPromptResult(output, true, details?.enable_highlight)
    );
  }, [promptRunStatus, isSinglePassExtractLoading, details?.enable_highlight]);

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

  const handleClick = (highlightData, key) => {
    if (highlightData && highlightData[key]) {
      handleSelectHighlight(
        highlightData[key],
        promptDetails?.prompt_id,
        profileId
      );
    }
  };

  const isObject = (value) =>
    typeof value === "object" && value !== null && !Array.isArray(value);

  const renderJson = (data, highlightData, indent = 0) => {
    console.log(data);
    if (typeof data === "object" && !details?.enable_highlight) {
      return JSON.stringify(data, null, 4);
    }

    if (typeof data === "string") {
      return `"${data}"`;
    }

    if (typeof data === "number" || typeof data === "boolean") {
      return data.toString();
    }

    if (Array.isArray(data)) {
      return (
        <>
          {"["}
          <div style={{ paddingLeft: "20px" }}>
            {data.map((item, index) => (
              <div key={index}>
                {renderJson(item, highlightData[index], indent + 1)}
                {index < data.length - 1 ? "," : ""}
              </div>
            ))}
          </div>
          {"]"}
        </>
      );
    }

    if (isObject(data)) {
      return (
        <>
          {"{"}
          <div style={{ paddingLeft: "20px" }}>
            {Object.entries(data).map(([key, value], index, array) => {
              const isClickable = !isObject(value) && !Array.isArray(value); // Only primitive values should be clickable

              return (
                <div key={key}>
                  <span
                    className="json-key"
                    style={{
                      color:
                        isClickable && highlightData?.[key] ? "blue" : "black",
                      cursor:
                        isClickable && highlightData?.[key]
                          ? "pointer"
                          : "default",
                    }}
                    onClick={() => {
                      if (isClickable && highlightData?.[key]) {
                        handleClick(highlightData, key);
                      }
                    }}
                  >
                    {key}
                  </span>
                  {": "}
                  {renderJson(value, highlightData?.[key], indent + 1)}
                  {index < array.length - 1 ? "," : ""}
                </div>
              );
            })}
          </div>
          {"}"}
        </>
      );
    }

    return String(data);
  };

  return (
    <Typography.Paragraph className="prompt-card-display-output font-size-12">
      {parsedOutput && typeof parsedOutput === "object" ? (
        renderJson(parsedOutput, highlightData, 0)
      ) : (
        <div>{parsedOutput && parsedOutput}</div>
      )}
    </Typography.Paragraph>
  );
}

DisplayPromptResult.propTypes = {
  output: PropTypes.any,
  profileId: PropTypes.string,
  docId: PropTypes.string,
  promptRunStatus: PropTypes.object,
  handleSelectHighlight: PropTypes.func,
  highlightData: PropTypes.object,
  promptDetails: PropTypes.object,
};

export { DisplayPromptResult };
