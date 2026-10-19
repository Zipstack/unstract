import { Info } from "lucide-react";
import PropTypes from "prop-types";
import { Fragment, useMemo, useState } from "react";
import { Space } from "@/components/ui/shims/antd-layout";
import { Spin } from "@/components/ui/shims/antd-leaves";
import { Typography } from "@/components/ui/shims/antd-typography";

import {
  displayPromptResult,
  generateApiRunStatusId,
  PROMPT_RUN_API_STATUSES,
} from "../../../helpers/GetStaticData";
import "./PromptCard.css";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

const RENDER_CAP = 50;

function CappedArray({ data, renderItem, totalCount }) {
  const [visibleCount, setVisibleCount] = useState(
    Math.min(RENDER_CAP, totalCount),
  );

  const remaining = totalCount - visibleCount;

  const showMoreLink = remaining > 0 && (
    <Typography.Link
      className="font-size-12"
      onClick={() =>
        setVisibleCount((prev) => Math.min(prev + RENDER_CAP, totalCount))
      }
    >
      ...show more ({remaining} remaining)
    </Typography.Link>
  );

  return (
    <>
      {"["}
      <div style={{ paddingLeft: "20px" }}>
        {remaining > 0 && (
          <div
            className="font-size-12"
            style={{
              color: "var(--text-tertiary, #888)",
              padding: "2px 0 4px",
            }}
          >
            Showing {visibleCount} of {totalCount} items — {showMoreLink}
          </div>
        )}
        {data.slice(0, visibleCount).map((item, index) => (
          <div key={index}>
            {renderItem(item, index)}
            {index < totalCount - 1 ? "," : ""}
          </div>
        ))}
        {showMoreLink}
      </div>
      {"]"}
    </>
  );
}

CappedArray.propTypes = {
  data: PropTypes.array.isRequired,
  renderItem: PropTypes.func.isRequired,
  totalCount: PropTypes.number.isRequired,
};

function DisplayPromptResult({
  output,
  profileId,
  docId,
  promptRunStatus,
  handleSelectHighlight,
  highlightData,
  promptDetails,
  confidenceData,
  wordConfidenceData,
  isTable = false,
  setOpenExpandModal = () => {
    // No-op default
  },
  progressMsg,
}) {
  const [selectedKey, setSelectedKey] = useState(null);
  const {
    singlePassExtractMode,
    isSinglePassExtractLoading,
    details,
    selectedHighlight,
  } = useCustomToolStore();

  // Derived — no state updates, so no render-loop risk.
  const statusKey = generateApiRunStatusId(docId, profileId);
  const isLoading =
    (singlePassExtractMode && isSinglePassExtractLoading) ||
    promptRunStatus?.[statusKey] === PROMPT_RUN_API_STATUSES.RUNNING;

  const parsedOutput = useMemo(() => {
    if (isLoading || output === undefined || output === null) {
      return null;
    }
    const isFormattingRequired = !isTable;
    return displayPromptResult(
      output,
      isFormattingRequired,
      details?.enable_highlight,
    );
  }, [output, isTable, details?.enable_highlight, isLoading]);

  if (isLoading) {
    return (
      <div className="prompt-loading-container">
        <Spin indicator={<SpinnerLoader size="small" />} />
        {progressMsg?.message && (
          <Typography.Text
            className="prompt-progress-msg"
            type={progressMsg?.level === "ERROR" ? "danger" : "secondary"}
          >
            {progressMsg.message}
          </Typography.Text>
        )}
      </div>
    );
  }

  if (output === undefined) {
    return (
      <Typography.Text className="prompt-not-ran">
        <span>
          <Info className="info-circle-colored" />
        </span>{" "}
        Yet to run
      </Typography.Text>
    );
  }

  if (output === null) {
    return (
      <Typography.Text className="prompt-output-result">null</Typography.Text>
    );
  }

  // Extract confidence from 5th element of highlight data coordinate arrays
  const extractConfidenceFromHighlightData = (data) => {
    if (!data) {
      return null;
    }

    const confidenceValues = [];

    const extractFromArray = (arr) => {
      if (Array.isArray(arr)) {
        for (const item of arr) {
          if (Array.isArray(item)) {
            // Check if this is a coordinate array with 5 elements
            if (item.length >= 5 && typeof item[4] === "number") {
              confidenceValues.push(item[4]);
            } else {
              // Recursively check nested arrays
              extractFromArray(item);
            }
          } else if (typeof item === "object" && item !== null) {
            // Recursively check objects
            for (const val of Object.values(item)) {
              extractFromArray(val);
            }
          }
        }
      } else if (typeof arr === "object" && arr !== null) {
        for (const val of Object.values(arr)) {
          extractFromArray(val);
        }
      }
    };

    extractFromArray(data);

    // Calculate average confidence if we found any values
    if (confidenceValues.length > 0) {
      const sum = confidenceValues.reduce((acc, val) => acc + val, 0);
      return sum / confidenceValues.length;
    }

    return null;
  };

  const handleClick = (
    highlightData,
    confidenceData,
    wordConfidenceData,
    key,
    keyPath,
  ) => {
    if (highlightData?.[key]) {
      const shouldUseWordConfidence =
        details?.enable_highlight && details?.enable_word_confidence;

      const getNestedValue = (obj, path) => {
        if (!obj || !path) {
          return undefined;
        }
        const normalized = path.replace(/\[(\d+)\]/g, ".$1");
        const parts = normalized.split(".").filter((p) => p !== "");
        return parts.reduce((acc, part) => {
          if (acc === undefined || acc === null) {
            return undefined;
          }
          const maybeIndex = /^\d+$/.test(part) ? Number(part) : part;
          return acc[maybeIndex];
        }, obj);
      };

      let confidence;
      if (shouldUseWordConfidence && wordConfidenceData) {
        const wordConfidence = getNestedValue(wordConfidenceData, key);
        if (wordConfidence && typeof wordConfidence === "object") {
          const values = Object.values(wordConfidence).filter(
            (v) => typeof v === "number",
          );
          if (values.length > 0) {
            const sum = values.reduce((acc, val) => acc + val, 0);
            confidence = sum / values.length;
          }
        }
      }

      if (confidence === undefined) {
        const extractedConfidence = extractConfidenceFromHighlightData(
          highlightData[key],
        );
        confidence = extractedConfidence ?? confidenceData?.[key];
      }

      handleSelectHighlight(
        highlightData[key],
        promptDetails?.prompt_id,
        profileId,
        confidence,
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
    wordConfidenceData,
    indent = 0,
    path = "",
    isTable = false,
  ) => {
    try {
      if (isTable) {
        const stringData =
          typeof data === "string" ? data : JSON.stringify(data, null, 4);
        const lines = stringData.split("\n");
        const truncated = lines.slice(0, 25).join("\n");
        return (
          <div>
            {truncated}
            {lines.length > 25 && (
              <Typography.Link
                className="font-size-12"
                onClick={() => {
                  setOpenExpandModal(true);
                }}
              >
                ...show more
              </Typography.Link>
            )}
          </div>
        );
      }
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
        const renderArrayItem = (item, index) =>
          renderJson(
            item,
            highlightData?.[index],
            confidenceData?.[index],
            wordConfidenceData?.[index],
            indent + 1,
            `${path}[${index}]`,
            isTable,
          );

        if (data.length > RENDER_CAP) {
          return (
            <CappedArray
              data={data}
              totalCount={data.length}
              renderItem={renderArrayItem}
            />
          );
        }
        return (
          <>
            {"["}
            <div style={{ paddingLeft: "20px" }}>
              {data?.map((item, index) => (
                <div key={index}>
                  {renderArrayItem(item, index)}
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
                            wordConfidenceData,
                            key,
                            newPath,
                          );
                        }
                      }}
                    >
                      {renderJson(
                        value,
                        highlightData?.[key],
                        confidenceData?.[key],
                        wordConfidenceData?.[key],
                        indent + 1,
                        newPath,
                        isTable,
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
    } catch {
      return (
        <Typography.Text type="danger">Unable to render output</Typography.Text>
      );
    }
  };

  return (
    <Typography.Paragraph className="prompt-card-display-output font-size-12">
      {parsedOutput && typeof parsedOutput === "object" ? (
        <Fragment key={`${docId}-${profileId}`}>
          {renderJson(
            parsedOutput,
            highlightData,
            confidenceData,
            wordConfidenceData,
            0,
            "",
            isTable,
          )}
        </Fragment>
      ) : (
        <TextResult
          enableHighlight={details?.enable_highlight}
          highlightData={highlightData}
          promptId={promptDetails?.prompt_id}
          profileId={profileId}
          wordConfidenceData={wordConfidenceData}
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
  wordConfidenceData,
  selectedHighlight,
  parsedOutput,
  onSelectHighlight,
}) => {
  const getConfidenceForText = () => {
    // Try word confidence first
    if (wordConfidenceData && typeof wordConfidenceData === "object") {
      const values = Object.values(wordConfidenceData).filter(
        (v) => typeof v === "number",
      );
      if (values.length > 0) {
        const sum = values.reduce((acc, val) => acc + val, 0);
        return sum / values.length;
      }
    }

    // Fallback to extracting from highlight data
    if (highlightData) {
      const confidenceValues = [];

      const extractConfidenceFromHighlightData = (data) => {
        if (Array.isArray(data)) {
          for (const item of data) {
            if (Array.isArray(item)) {
              if (item.length >= 5 && typeof item[4] === "number") {
                confidenceValues.push(item[4]);
              } else {
                extractConfidenceFromHighlightData(item);
              }
            } else if (typeof item === "object" && item !== null) {
              for (const val of Object.values(item)) {
                extractConfidenceFromHighlightData(val);
              }
            }
          }
        } else if (typeof data === "object" && data !== null) {
          for (const val of Object.values(data)) {
            extractConfidenceFromHighlightData(val);
          }
        }
      };

      extractConfidenceFromHighlightData(highlightData);

      if (confidenceValues.length > 0) {
        const sum = confidenceValues.reduce((acc, val) => acc + val, 0);
        return sum / confidenceValues.length;
      }
    }

    return undefined;
  };

  const confidence = getConfidenceForText();

  return enableHighlight ? (
    <Typography.Text
      wrap
      onClick={() =>
        onSelectHighlight(highlightData, promptId, profileId, confidence)
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
  wordConfidenceData: PropTypes.any,
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
  highlightData: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  promptDetails: PropTypes.object,
  confidenceData: PropTypes.object,
  wordConfidenceData: PropTypes.object,
  isTable: PropTypes.bool,
  setOpenExpandModal: PropTypes.func,
  progressMsg: PropTypes.object,
};

export { DisplayPromptResult };
