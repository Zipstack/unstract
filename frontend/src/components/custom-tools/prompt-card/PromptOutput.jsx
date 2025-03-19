import {
  CheckCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleFilled,
  InfoCircleOutlined,
  PlayCircleFilled,
  PlayCircleOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";
import {
  Button,
  Col,
  Divider,
  Image,
  Radio,
  Space,
  Tooltip,
  Typography,
} from "antd";
import { motion, AnimatePresence } from "framer-motion";
import CheckableTag from "antd/es/tag/CheckableTag";

import {
  displayPromptResult,
  generateApiRunStatusId,
  PROMPT_RUN_API_STATUSES,
  PROMPT_RUN_TYPES,
} from "../../../helpers/GetStaticData";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useWindowDimensions } from "../../../hooks/useWindowDimensions";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { TABLE_ENFORCE_TYPE, RECORD_ENFORCE_TYPE } from "./constants";
import { CopyPromptOutputBtn } from "./CopyPromptOutputBtn";
import { useAlertStore } from "../../../store/alert-store";
import { PromptOutputExpandBtn } from "./PromptOutputExpandBtn";
import { DisplayPromptResult } from "./DisplayPromptResult";
import usePromptOutput from "../../../hooks/usePromptOutput";
import { PromptRunTimer } from "./PromptRunTimer";
import { PromptRunCost } from "./PromptRunCost";

let TableOutput;
try {
  TableOutput = require("../../../plugins/prompt-card/TableOutput").TableOutput;
} catch {
  // The component will remain null of it is not available
}
let ChallengeModal;
try {
  ChallengeModal =
    require("../../../plugins/challenge-modal/ChallengeModal").ChallengeModal;
} catch {
  // The component will remain null of it is not available
}

function PromptOutput({
  promptDetails,
  handleRun,
  selectedLlmProfileId,
  handleSelectDefaultLLM,
  llmProfileDetails,
  setOpenIndexProfile,
  enabledProfiles,
  setEnabledProfiles,
  isNotSingleLlmProfile,
  setIsIndexOpen,
  enforceType,
  promptOutputs,
  promptRunStatus,
  isChallenge,
  handleSelectHighlight,
}) {
  const { width: windowWidth } = useWindowDimensions();
  const componentWidth = windowWidth * 0.4;
  const {
    selectedDoc,
    singlePassExtractMode,
    isSimplePromptStudio,
    isPublicSource,
    defaultLlmProfile,
    selectedHighlight,
    details,
  } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const { generatePromptOutputKey } = usePromptOutput();
  const isTableExtraction =
    enforceType === TABLE_ENFORCE_TYPE || enforceType === RECORD_ENFORCE_TYPE;
  const noHighlightEnforceType = !["table", "record"].includes(enforceType);
  const tooltipContent = (adapterConf) => (
    <div>
      {Object.entries(adapterConf)?.map(([key, value]) => (
        <div key={key}>
          <strong>{key}:</strong> {value}
        </div>
      ))}
    </div>
  );

  const handleTagChange = (checked, profileId) => {
    setEnabledProfiles((prevState) =>
      checked
        ? [...prevState, profileId]
        : prevState.filter((id) => id !== profileId)
    );
  };

  const getColSpan = () => (componentWidth < 1200 ? 24 : 6);

  const copyOutputToClipboard = (text) => {
    if (!text || text === "undefined" || isTableExtraction) {
      return;
    }

    navigator.clipboard
      .writeText(text)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Prompt output copied successfully",
        });
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Failed to copy prompt output",
        });
      });
  };

  if (
    (singlePassExtractMode || isSimplePromptStudio) &&
    (promptDetails?.active || isSimplePromptStudio)
  ) {
    const promptId = promptDetails?.prompt_id;
    const docId = selectedDoc?.document_id;
    const promptOutputKey = generatePromptOutputKey(
      promptId,
      docId,
      defaultLlmProfile,
      singlePassExtractMode,
      true
    );

    const promptOutput = promptOutputs[promptOutputKey]?.output;

    let promptOutputData = {};
    if (promptOutputs && Object.keys(promptOutputs)) {
      const promptOutputKey = generatePromptOutputKey(
        promptId,
        docId,
        defaultLlmProfile,
        singlePassExtractMode,
        true
      );
      if (promptOutputs[promptOutputKey] !== undefined) {
        promptOutputData = promptOutputs[promptOutputKey];
      }
    }

    return (
      <>
        <Divider className="prompt-card-divider" />
        <Space
          wrap
          className={`prompt-card-result prompt-card-div ${
            details?.enable_highlight &&
            noHighlightEnforceType &&
            selectedHighlight?.highlightedPrompt === promptId &&
            selectedHighlight?.highlightedProfile === defaultLlmProfile &&
            "highlighted-prompt-cell"
          }`}
        >
          <DisplayPromptResult
            output={promptOutput}
            highlightData={
              promptOutputData?.highlightData?.[promptDetails.prompt_key]
            }
            handleSelectHighlight={handleSelectHighlight}
            confidenceData={
              promptOutputData?.confidenceData?.[promptDetails.prompt_key]
            }
          />
          <div className="prompt-profile-run">
            <CopyPromptOutputBtn
              isDisabled={isTableExtraction}
              copyToClipboard={() =>
                copyOutputToClipboard(
                  displayPromptResult(
                    promptOutput,
                    true,
                    promptDetails?.enable_highlight
                  )
                )
              }
            />
            <PromptOutputExpandBtn
              promptId={promptDetails?.prompt_id}
              llmProfiles={llmProfileDetails}
              enforceType={enforceType}
              displayLlmProfile={false}
              promptOutputs={promptOutputs}
              promptRunStatus={promptRunStatus}
            />
          </div>
        </Space>
      </>
    );
  }

  return (
    <AnimatePresence>
      {!singlePassExtractMode &&
        !isSimplePromptStudio &&
        llmProfileDetails.map((profile, index) => {
          const promptId = promptDetails?.prompt_id;
          const docId = selectedDoc?.document_id;
          const profileId = profile?.profile_id;
          const isChecked = enabledProfiles.includes(profileId);
          const tokenUsageId = promptId + "__" + docId + "__" + profileId;
          let promptOutputData = {};
          if (promptOutputs && Object.keys(promptOutputs)) {
            const promptOutputKey = generatePromptOutputKey(
              promptId,
              docId,
              profileId,
              singlePassExtractMode,
              true
            );
            if (promptOutputs[promptOutputKey] !== undefined) {
              promptOutputData = promptOutputs[promptOutputKey];
            }
          }

          const isPromptLoading =
            promptRunStatus?.[generateApiRunStatusId(docId, profileId)] ===
            PROMPT_RUN_API_STATUSES.RUNNING;
          return (
            <motion.div
              key={profileId}
              initial={{ x: 0 }}
              animate={{
                x: profileId === selectedLlmProfileId && index !== 0 ? -10 : 0,
              }}
              transition={{ duration: 0.5, ease: "linear" }}
              className={`prompt-card-llm ${
                details?.enable_highlight &&
                noHighlightEnforceType &&
                selectedHighlight?.highlightedPrompt === promptId &&
                selectedHighlight?.highlightedProfile === profileId &&
                "highlighted-prompt-cell"
              }`}
            >
              <Col
                key={profileId}
                className="prompt-card-llm-container"
                xs={{ span: getColSpan() }}
              >
                <Divider className="prompt-card-divider" />
                <Space
                  direction="vertical"
                  className="prompt-card-llm-layout"
                  onClick={() => {
                    enforceType !== "json" &&
                      handleSelectHighlight(
                        promptOutputData?.highlightData,
                        promptId,
                        profileId,
                        promptOutputData?.confidenceData
                      );
                  }}
                >
                  <div className="llm-info">
                    <div className="llm-info-left">
                      <Image
                        src={profile?.icon}
                        width={15}
                        height={15}
                        preview={false}
                        className="prompt-card-llm-icon"
                      />
                      <Typography.Text
                        className="prompt-card-llm-title"
                        ellipsis={{ tooltip: profile?.conf?.LLM }}
                      >
                        {profile?.conf?.LLM}
                      </Typography.Text>
                    </div>
                    <div className="llm-info-right">
                      <Space>
                        <Tooltip title={tooltipContent(profile?.conf)}>
                          <InfoCircleOutlined className="prompt-card-actions-head" />
                        </Tooltip>
                        <Tooltip title="Chunk used">
                          <DatabaseOutlined
                            onClick={() => {
                              setIsIndexOpen(true);
                              setOpenIndexProfile(promptOutputData?.context);
                            }}
                            className="prompt-card-actions-head"
                          />
                        </Tooltip>
                        {ChallengeModal && isChallenge && (
                          <ChallengeModal
                            challengeData={
                              promptOutputData?.challengeData || {}
                            }
                            context={promptOutputData?.context || ""}
                            tokenUsage={promptOutputData?.tokenUsage || {}}
                          />
                        )}
                        {isNotSingleLlmProfile && (
                          <Tooltip title="Select Default">
                            <Radio
                              checked={profileId === selectedLlmProfileId}
                              onChange={() => handleSelectDefaultLLM(profileId)}
                              disabled={isPublicSource}
                            />
                          </Tooltip>
                        )}
                      </Space>
                    </div>
                  </div>
                  <div className="prompt-cost">
                    <Typography.Text className="prompt-cost-item">
                      Tokens:{" "}
                      {!singlePassExtractMode && (
                        <TokenUsage
                          tokenUsageId={tokenUsageId}
                          isLoading={isPromptLoading}
                        />
                      )}
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      <PromptRunTimer
                        timer={promptOutputData?.timer}
                        isLoading={isPromptLoading}
                      />
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      <PromptRunCost
                        tokenUsage={promptOutputData?.tokenUsage}
                        isLoading={isPromptLoading}
                      />
                    </Typography.Text>
                  </div>
                  <div className="prompt-info">
                    <div>
                      <CheckableTag
                        checked={isChecked}
                        onChange={(checked) =>
                          handleTagChange(checked, profileId)
                        }
                        disabled={isPublicSource}
                        className={isChecked ? "checked" : "unchecked"}
                      >
                        {isChecked ? (
                          <span>
                            Enabled
                            <CheckCircleOutlined className="prompt-output-icon-enabled" />
                          </span>
                        ) : (
                          <span>
                            Disabled
                            <ExclamationCircleFilled className="prompt-output-icon-disabled" />
                          </span>
                        )}
                      </CheckableTag>
                    </div>
                    <div>
                      <Tooltip title="Run LLM for current document">
                        <Button
                          size="small"
                          type="text"
                          className="prompt-card-action-button"
                          onClick={() =>
                            handleRun(
                              PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ONE_DOC,
                              promptDetails?.prompt_id,
                              profileId,
                              selectedDoc?.document_id
                            )
                          }
                          disabled={isPromptLoading || isPublicSource}
                        >
                          <PlayCircleOutlined className="prompt-card-actions-head" />
                        </Button>
                      </Tooltip>
                      <Tooltip title="Run LLM for all documents">
                        <Button
                          size="small"
                          type="text"
                          className="prompt-card-action-button"
                          onClick={() =>
                            handleRun(
                              PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ALL_DOCS,
                              promptDetails?.prompt_id,
                              profileId,
                              null
                            )
                          }
                          disabled={isPromptLoading || isPublicSource}
                        >
                          <PlayCircleFilled className="prompt-card-actions-head" />
                        </Button>
                      </Tooltip>
                      <PromptOutputExpandBtn
                        promptId={promptDetails?.prompt_id}
                        llmProfiles={llmProfileDetails}
                        enforceType={enforceType}
                        displayLlmProfile={true}
                        promptOutputs={promptOutputs}
                        promptRunStatus={promptRunStatus}
                      />
                    </div>
                  </div>
                </Space>
                <>
                  <Divider className="prompt-card-divider" />
                  <div className="prompt-card-result prompt-card-div">
                    {isTableExtraction && TableOutput ? (
                      <TableOutput output={promptOutputData?.output} />
                    ) : (
                      <>
                        <DisplayPromptResult
                          output={promptOutputData?.output}
                          profileId={profileId}
                          docId={selectedDoc?.document_id}
                          promptRunStatus={promptRunStatus}
                          handleSelectHighlight={handleSelectHighlight}
                          highlightData={promptOutputData?.highlightData}
                          confidenceData={promptOutputData?.confidenceData}
                          promptDetails={promptDetails}
                        />
                        <div className="prompt-profile-run">
                          <CopyPromptOutputBtn
                            isDisabled={isTableExtraction}
                            copyToClipboard={() =>
                              copyOutputToClipboard(
                                displayPromptResult(
                                  promptOutputData?.output,
                                  true
                                )
                              )
                            }
                          />
                        </div>
                      </>
                    )}
                  </div>
                </>
              </Col>
            </motion.div>
          );
        })}
    </AnimatePresence>
  );
}

PromptOutput.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleSelectDefaultLLM: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  llmProfileDetails: PropTypes.array.isRequired,
  setOpenIndexProfile: PropTypes.func.isRequired,
  enabledProfiles: PropTypes.array.isRequired,
  setEnabledProfiles: PropTypes.func.isRequired,
  isNotSingleLlmProfile: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
  enforceType: PropTypes.string,
  promptOutputs: PropTypes.object.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
  isChallenge: PropTypes.bool,
  handleSelectHighlight: PropTypes.func.isRequired,
};

export { PromptOutput };
