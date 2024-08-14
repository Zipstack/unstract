import {
  ArrowsAltOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleFilled,
  InfoCircleFilled,
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

import {
  displayPromptResult,
  getFormattedTotalCost,
} from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useWindowDimensions } from "../../../hooks/useWindowDimensions";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { TABLE_ENFORCE_TYPE } from "./constants";

let TableOutput;
try {
  TableOutput = require("../../../plugins/prompt-card/TableOutput").TableOutput;
} catch {
  // The component will remain null of it is not available
}

function PromptOutput({
  promptDetails,
  isRunLoading,
  result,
  handleRun,
  selectedLlmProfileId,
  handleSelectDefaultLLM,
  timers,
  spsLoading,
  llmProfileDetails,
  setOpenIndexProfile,
  enabledProfiles,
  setEnabledProfiles,
  expandedProfiles,
  setExpandedProfiles,
  isNotSingleLlmProfile,
  setIsIndexOpen,
  enforceType,
}) {
  const [firstResult] = result || [];
  const { width: windowWidth } = useWindowDimensions();
  const componentWidth = windowWidth * 0.4;
  const {
    selectedDoc,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    isSimplePromptStudio,
    isPublicSource,
  } = useCustomToolStore();

  const tooltipContent = (adapterConf) => (
    <div>
      {Object.entries(adapterConf)?.map(([key, value]) => (
        <div key={key}>
          <strong>{key}:</strong> {value}
        </div>
      ))}
    </div>
  );

  const handleExpandClick = (profile) => {
    const profileId = profile?.profile_id;
    setExpandedProfiles((prevState) =>
      prevState.includes(profileId)
        ? prevState.filter((id) => id !== profileId)
        : [...prevState, profileId]
    );
  };

  const handleTagChange = (checked, profileId) => {
    setEnabledProfiles((prevState) =>
      checked
        ? [...prevState, profileId]
        : prevState.filter((id) => id !== profileId)
    );
  };

  const getColSpan = () => (componentWidth < 1200 ? 24 : 6);

  if (
    (singlePassExtractMode || isSimplePromptStudio) &&
    (promptDetails.active || isSimplePromptStudio) &&
    (firstResult?.output ||
      firstResult?.output === 0 ||
      spsLoading[selectedDoc?.document_id])
  ) {
    return (
      <>
        <Divider className="prompt-card-divider" />
        <div
          className={`prompt-card-result prompt-card-div ${
            expandedProfiles.includes(firstResult?.profileManager) &&
            "prompt-profile-run-expanded"
          }`}
        >
          {isSinglePassExtractLoading ||
          spsLoading[selectedDoc?.document_id] ? (
            <Spin indicator={<SpinnerLoader size="small" />} />
          ) : (
            <Typography.Paragraph className="prompt-card-res font-size-12">
              <div
                className={
                  expandedProfiles.includes(firstResult.profileManager)
                    ? "expanded-output"
                    : "collapsed-output"
                }
              >
                {displayPromptResult(firstResult.output, true)}
              </div>
            </Typography.Paragraph>
          )}
          <div className="prompt-profile-run">
            <Tooltip title="Expand">
              <Button
                size="small"
                type="text"
                className="prompt-card-action-button"
                onClick={() =>
                  handleExpandClick({
                    profile_id: firstResult.profileManager,
                  })
                }
              >
                <ArrowsAltOutlined className="prompt-card-actions-head" />
              </Button>
            </Tooltip>
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
          const profileId = profile?.profile_id;
          const isChecked = enabledProfiles.includes(profileId);
          const tokenUsageId =
            promptDetails?.prompt_id +
            "__" +
            selectedDoc?.document_id +
            "__" +
            profileId;
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
                    <Typography.Title
                      className="prompt-card-llm-title"
                      level={5}
                    >
                      {profile?.conf?.LLM}
                    </Typography.Title>
                  </div>
                  <div className="prompt-cost">
                    <Typography.Text className="prompt-cost-item">
                      Tokens:{" "}
                      {!singlePassExtractMode && (
                        <TokenUsage tokenUsageId={tokenUsageId} />
                      )}
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      Time: {timers[tokenUsageId] || 0}s
                    </Typography.Text>
                    <Typography.Text className="prompt-cost-item">
                      Cost: ${getFormattedTotalCost(result, profile)}
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
                        <InfoCircleOutlined />
                      </Tooltip>
                      <Tooltip title="Chunk used">
                        <DatabaseOutlined
                          onClick={() => {
                            setIsIndexOpen(true);
                            setOpenIndexProfile(
                              result.find(
                                (r) => r?.profileManager === profileId
                              )?.context
                            );
                          }}
                          className="prompt-card-actions-head"
                        />
                      </Tooltip>
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
                  <div
                    className={`prompt-card-result prompt-card-div ${
                      expandedProfiles.includes(profileId) &&
                      "prompt-profile-run-expanded"
                    }`}
                  >
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
                            <div
                              className={
                                expandedProfiles.includes(profileId)
                                  ? "expanded-output"
                                  : "collapsed-output"
                              }
                            >
                              {!result.find(
                                (r) => r?.profileManager === profileId
                              )?.output ? (
                                <Typography.Text className="prompt-not-ran">
                                  <span>
                                    <InfoCircleFilled
                                      style={{ color: "#F0AD4E" }}
                                    />
                                  </span>{" "}
                                  Yet to run
                                </Typography.Text>
                              ) : (
                                displayPromptResult(
                                  result.find(
                                    (r) => r?.profileManager === profileId
                                  )?.output,
                                  true
                                )
                              )}
                            </div>
                          </Typography.Paragraph>
                        )}
                      </>
                    )}
                    <div className="prompt-profile-run">
                      <>
                        <Tooltip title="Run">
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
                        <Tooltip title="Run All">
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
                      </>
                      <Tooltip title="Expand">
                        <Button
                          size="small"
                          type="text"
                          className="prompt-card-action-button"
                          onClick={() => handleExpandClick(profile)}
                        >
                          <ArrowsAltOutlined className="prompt-card-actions-head" />
                        </Button>
                      </Tooltip>
                    </div>
                  </div>
                  {enforceType === TABLE_ENFORCE_TYPE && <TableOutput />}
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
  result: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleSelectDefaultLLM: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  timers: PropTypes.object.isRequired,
  spsLoading: PropTypes.object,
  llmProfileDetails: PropTypes.array.isRequired,
  setOpenIndexProfile: PropTypes.func.isRequired,
  enabledProfiles: PropTypes.array.isRequired,
  setEnabledProfiles: PropTypes.func.isRequired,
  expandedProfiles: PropTypes.array.isRequired,
  setExpandedProfiles: PropTypes.func.isRequired,
  isNotSingleLlmProfile: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
  enforceType: PropTypes.string.isRequired,
};

export { PromptOutput };
