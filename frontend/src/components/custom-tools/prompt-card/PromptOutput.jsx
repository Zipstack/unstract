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
  Spin,
  Tooltip,
  Typography,
} from "antd";
import { motion, AnimatePresence } from "framer-motion";
import CheckableTag from "antd/es/tag/CheckableTag";

import { displayPromptResult } from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useWindowDimensions } from "../../../hooks/useWindowDimensions";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { TABLE_ENFORCE_TYPE } from "./constants";
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
  isRunLoading,
  handleRun,
  selectedLlmProfileId,
  handleSelectDefaultLLM,
  timers,
  spsLoading,
  llmProfileDetails,
  setOpenIndexProfile,
  enabledProfiles,
  setEnabledProfiles,
  isNotSingleLlmProfile,
  setIsIndexOpen,
  enforceType,
  promptOutputs,
}) {
  const { width: windowWidth } = useWindowDimensions();
  const componentWidth = windowWidth * 0.4;
  const {
    selectedDoc,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
    isPublicSource,
    defaultLlmProfile,
  } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const { generatePromptOutputKey } = usePromptOutput();

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
    if (!text || text === "undefined" || enforceType === TABLE_ENFORCE_TYPE) {
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

    return (
      <>
        <Divider className="prompt-card-divider" />
        <div className="prompt-card-result prompt-card-div">
          {isSinglePassExtractLoading ||
          spsLoading[selectedDoc?.document_id] ? (
            <Spin indicator={<SpinnerLoader size="small" />} />
          ) : (
            <Typography.Paragraph className="prompt-card-res font-size-12">
              <div className="expanded-output">
                <DisplayPromptResult output={promptOutput} />
              </div>
            </Typography.Paragraph>
          )}
          <div className="prompt-profile-run">
            <CopyPromptOutputBtn
              isDisabled={enforceType === TABLE_ENFORCE_TYPE}
              copyToClipboard={() =>
                copyOutputToClipboard(displayPromptResult(promptOutput, true))
              }
            />
            <PromptOutputExpandBtn
              promptId={promptDetails?.prompt_id}
              llmProfiles={llmProfileDetails}
              enforceType={enforceType}
              displayLlmProfile={false}
              promptOutputs={promptOutputs}
            />
          </div>
        </div>
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
          return (
            <motion.div
              key={profileId}
              initial={{ x: 0 }}
              animate={{
                x: profileId === selectedLlmProfileId && index !== 0 ? -10 : 0,
              }}
              transition={{ duration: 0.5, ease: "linear" }}
              className="prompt-card-llm"
            >
              <Col
                key={profileId}
                className="prompt-card-llm-container"
                xs={{ span: getColSpan() }}
              >
                <Divider className="prompt-card-divider" />
                <Space direction="vertical" className="prompt-card-llm-layout">
                  <div className="llm-info">
                    <Image
                      src={profile?.icon}
                      width={15}
                      height={15}
                      preview={false}
                      className="prompt-card-llm-icon"
                    />
                    <Typography.Text className="prompt-card-llm-title">
                      {profile?.conf?.LLM}
                    </Typography.Text>
                  </div>
                  <div className="prompt-cost">
                    <Typography.Text className="prompt-cost-item">
                      Tokens:{" "}
                      {!singlePassExtractMode && (
                        <TokenUsage
                          tokenUsageId={tokenUsageId}
                          isLoading={
                            isRunLoading[
                              `${selectedDoc?.document_id}_${profileId}`
                            ]
                          }
                        />
                      )}
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      <PromptRunTimer
                        timer={timers[profileId]}
                        isLoading={
                          isRunLoading[
                            `${selectedDoc?.document_id}_${profileId}`
                          ]
                        }
                      />
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      <PromptRunCost
                        tokenUsage={promptOutputData?.tokenUsage}
                        isLoading={
                          isRunLoading[
                            `${selectedDoc?.document_id}_${profileId}`
                          ]
                        }
                      />
                    </Typography.Text>
                  </div>
                  <div className="prompt-info">
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
                          <CheckCircleOutlined
                            style={{
                              color: "#52c41a",
                              marginLeft: "5px",
                            }}
                          />
                        </span>
                      ) : (
                        <span>
                          Disabled
                          <ExclamationCircleFilled
                            style={{
                              color: "#BABBBC",
                              marginLeft: "5px",
                            }}
                          />
                        </span>
                      )}
                    </CheckableTag>
                    <div className="llm-info-container">
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
                      {ChallengeModal && (
                        <ChallengeModal
                          challengeData={promptOutputData?.challengeData || {}}
                          context={promptOutputData?.context || ""}
                          tokenUsage={promptOutputData?.tokenUsage || {}}
                        />
                      )}
                      {isNotSingleLlmProfile && (
                        <Radio
                          checked={profileId === selectedLlmProfileId}
                          onChange={() => handleSelectDefaultLLM(profileId)}
                          disabled={isPublicSource}
                        >
                          Default
                        </Radio>
                      )}
                    </div>
                  </div>
                </Space>
                <>
                  <Divider className="prompt-card-divider" />
                  <div className={"prompt-card-result prompt-card-div"}>
                    {enforceType === TABLE_ENFORCE_TYPE ? (
                      <div />
                    ) : (
                      <>
                        {isRunLoading[
                          `${selectedDoc?.document_id}_${profileId}`
                        ] ? (
                          <Spin indicator={<SpinnerLoader size="small" />} />
                        ) : (
                          <Typography.Paragraph className="prompt-card-res font-size-12">
                            <div className="expanded-output">
                              <DisplayPromptResult
                                output={promptOutputData?.output}
                              />
                            </div>
                          </Typography.Paragraph>
                        )}
                      </>
                    )}
                    <div className="prompt-profile-run">
                      <Tooltip title="Run LLM for current document">
                        <Button
                          size="small"
                          type="text"
                          className="prompt-card-action-button"
                          onClick={() => handleRun(profileId, false)}
                          disabled={
                            isRunLoading[
                              `${selectedDoc?.document_id}_${profileId}`
                            ] || isPublicSource
                          }
                        >
                          <PlayCircleOutlined className="prompt-card-actions-head" />
                        </Button>
                      </Tooltip>
                      <Tooltip title="Run LLM for all documents">
                        <Button
                          size="small"
                          type="text"
                          className="prompt-card-action-button"
                          onClick={() => handleRun(profileId, true)}
                          disabled={
                            isRunLoading[
                              `${selectedDoc?.document_id}_${profileId}`
                            ] || isPublicSource
                          }
                        >
                          <PlayCircleFilled className="prompt-card-actions-head" />
                        </Button>
                      </Tooltip>
                      <CopyPromptOutputBtn
                        isDisabled={enforceType === TABLE_ENFORCE_TYPE}
                        copyToClipboard={() =>
                          copyOutputToClipboard(
                            displayPromptResult(promptOutputData?.output, true)
                          )
                        }
                      />
                      <PromptOutputExpandBtn
                        promptId={promptDetails?.prompt_id}
                        llmProfiles={llmProfileDetails}
                        enforceType={enforceType}
                        displayLlmProfile={true}
                        promptOutputs={promptOutputs}
                      />
                    </div>
                  </div>
                  {enforceType === TABLE_ENFORCE_TYPE && TableOutput && (
                    <TableOutput output={promptOutputData?.output} />
                  )}
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
  isRunLoading: PropTypes.object,
  handleRun: PropTypes.func.isRequired,
  handleSelectDefaultLLM: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  timers: PropTypes.object.isRequired,
  spsLoading: PropTypes.object,
  llmProfileDetails: PropTypes.array.isRequired,
  setOpenIndexProfile: PropTypes.func.isRequired,
  enabledProfiles: PropTypes.array.isRequired,
  setEnabledProfiles: PropTypes.func.isRequired,
  isNotSingleLlmProfile: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
  enforceType: PropTypes.string.isRequired,
  promptOutputs: PropTypes.object.isRequired,
};

export { PromptOutput };
