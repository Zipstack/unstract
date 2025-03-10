import { Space, Spin, Typography } from "antd";
import PropTypes from "prop-types";
import { InfoCircleFilled } from "@ant-design/icons";
import { useEffect, useState } from "react";

import {
  displayPromptResult,
  generateApiRunStatusId,
  generateUUID,
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
  confidenceData,
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [parsedOutput, setParsedOutput] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const {
    singlePassExtractMode,
    isSinglePassExtractLoading,
    details,
    selectedHighlight,
  } = useCustomToolStore();

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
  }, [
    promptRunStatus,
    isSinglePassExtractLoading,
    details?.enable_highlight,
    output,
  ]);

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

  const handleClick = (highlightData, confidenceData, key, keyPath) => {
    if (highlightData?.[key]) {
      handleSelectHighlight(
        highlightData[key],
        promptDetails?.prompt_id,
        profileId,
        confidenceData?.[key]
      );
      setSelectedKey(keyPath);
    }
  };

  const isObject = (value) =>
    typeof value === "object" && value !== null && !Array.isArray(value);

  const renderJson = (
    data,
    highlightData,
    confidenceData,
    indent = 0,
    path = ""
  ) => {
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
              <div key={generateUUID()}>
                {renderJson(
                  item,
                  highlightData[index],
                  confidenceData?.[index],
                  indent + 1,
                  `${path}[${index}]`
                )}
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
              const newPath = path ? `${path}.${key}` : key;
              const isSelected = selectedKey === newPath;
              return (
                <div key={key}>
                  <Space wrap className="json-key">
                    {key}
                  </Space>
                  {": "}
                  <Typography.Text
                    className={`prompt-output-result json-value ${
                      isClickable && highlightData?.[key] ? "clickable" : ""
                    } ${isSelected ? "selected" : ""}`}
                    onClick={() => {
                      if (isClickable && highlightData?.[key]) {
                        handleClick(
                          highlightData,
                          confidenceData,
                          key,
                          newPath
                        );
                      }
                    }}
                  >
                    {renderJson(
                      value,
                      highlightData?.[key],
                      confidenceData?.[key],
                      indent + 1,
                      newPath
                    )}
                  </Typography.Text>
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
        renderJson(parsedOutput, highlightData, confidenceData, 0)
      ) : (
        <TextResult
          enableHighlight={details?.enable_highlight}
          highlightData={highlightData}
          promptId={promptDetails?.prompt_id}
          profileId={profileId}
          confidenceData={confidenceData}
          selectedHighlight={selectedHighlight}
          parsedOutput={parsedOutput}
          onSelectHighlight={handleSelectHighlight}
        />
      )}
    </Typography.Paragraph>
  );
}

const TextResult = ({
  enableHighlight,
  highlightData,
  promptId,
  profileId,
  confidenceData,
  selectedHighlight,
  parsedOutput,
  onSelectHighlight,
}) => {
  return enableHighlight ? (
    <Typography.Text
      wrap
      onClick={() =>
        onSelectHighlight(highlightData, promptId, profileId, confidenceData)
      }
      className={`prompt-output-result json-value ${
        highlightData ? "clickable" : ""
      } ${selectedHighlight?.highlightedPrompt === promptId ? "selected" : ""}`}
    >
      {parsedOutput}
    </Typography.Text>
  ) : (
    <div>{parsedOutput}</div>
  );
};

TextResult.propTypes = {
  enableHighlight: PropTypes.bool,
  highlightData: PropTypes.any,
  promptId: PropTypes.string,
  profileId: PropTypes.string,
  confidenceData: PropTypes.any,
  selectedHighlight: PropTypes.object,
  parsedOutput: PropTypes.any,
  onSelectHighlight: PropTypes.func.isRequired,
};
DisplayPromptResult.propTypes = {
  output: PropTypes.any,
  profileId: PropTypes.string,
  docId: PropTypes.string,
  promptRunStatus: PropTypes.object,
  handleSelectHighlight: PropTypes.func,
  highlightData: PropTypes.object,
  promptDetails: PropTypes.object,
  confidenceData: PropTypes.object,
};

export { DisplayPromptResult };
