import PropTypes from "prop-types";
import {
  ArrowsAltOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  ExclamationCircleFilled,
  InfoCircleOutlined,
  PlayCircleFilled,
  PlayCircleOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Image,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Tooltip,
  Typography,
} from "antd";
import { useEffect, useRef, useState } from "react";

import { displayPromptResult } from "../../../helpers/GetStaticData";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EditableText } from "../editable-text/EditableText";
import { TokenUsage } from "../token-usage/TokenUsage";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { Header } from "./Header";
import CheckableTag from "antd/es/tag/CheckableTag";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { motion, AnimatePresence } from "framer-motion";
import { OutputForIndex } from "./OutputForIndex";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";

const EvalBtn = null;
const EvalMetrics = null;

function useWindowDimensions() {
  const [windowDimensions, setWindowDimensions] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  useEffect(() => {
    function handleResize() {
      setWindowDimensions({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return windowDimensions;
}

function PromptCardItems({
  promptDetails,
  enforceTypeList,
  isRunLoading,
  promptKey,
  setPromptKey,
  promptText,
  setPromptText,
  result,
  coverage,
  progressMsg,
  handleRun,
  handleChange,
  handleDelete,
  handleTypeChange,
  updateStatus,
  updatePlaceHolder,
  isCoverageLoading,
  setOpenEval,
  setOpenOutputForDoc,
  selectedLlmProfileId,
  handleSelectDefaultLLM,
  timers,
}) {
  const {
    llmProfiles,
    selectedDoc,
    listOfDocs,
    disableLlmOrDocChange,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    indexDocs,
  } = useCustomToolStore();
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [expandCard, setExpandCard] = useState(true);
  const [llmProfileDetails, setLlmProfileDetails] = useState([]);
  const [openIndexProfile, setOpenIndexProfile] = useState(null);
  const [enabledProfiles, setEnabledProfiles] = useState(
    llmProfiles.map((profile) => profile.profile_id)
  );
  const [expandedProfiles, setExpandedProfiles] = useState([]); // New state for expanded profiles
  const [isIndexOpen, setIsIndexOpen] = useState(false);
  const privateAxios = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { width: windowWidth } = useWindowDimensions();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const componentWidth = windowWidth * 0.4;

  const divRef = useRef(null);

  const enableEdit = (event) => {
    event.stopPropagation();
    setExpandCard(true);
    setIsEditingTitle(true);
    setIsEditingPrompt(true);
  };
  const getModelOrAdapterId = (profile, adapters) => {
    const result = { conf: {} };
    const keys = ["vector_store", "embedding_model", "llm", "x2text"];

    keys.forEach((key) => {
      const adapterName = profile[key];
      const adapter = adapters.find(
        (adapter) => adapter.adapter_name === adapterName
      );
      if (adapter) {
        result.conf[key] = adapter.model || adapter.adapter_id.split("|")[0];
        if (adapter.adapter_type === "LLM") result.icon = adapter.icon;
      }
    });
    return result;
  };

  const getAdapterInfo = async () => {
    privateAxios
      .get(`/api/v1/unstract/${sessionDetails.orgId}/adapter/`)
      .then((res) => {
        const adapterData = res.data;

        // Update llmProfiles with additional fields
        const updatedProfiles = llmProfiles.map((profile) => {
          return { ...getModelOrAdapterId(profile, adapterData), ...profile };
        });
        setLlmProfileDetails(
          updatedProfiles
            .map((profile) => ({
              ...profile,
              isDefault: profile.profile_id === selectedLlmProfileId,
              isEnabled: enabledProfiles.includes(profile.profile_id),
            }))
            .sort((a, b) => {
              if (a.isDefault) return -1; // Default profile comes first
              if (b.isDefault) return 1;
              if (a.isEnabled && !b.isEnabled) return -1; // Enabled profiles come before disabled
              if (!a.isEnabled && b.isEnabled) return 1;
              return 0;
            })
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const tooltipContent = (adapterConf) => (
    <div>
      {Object.entries(adapterConf).map(([key, value]) => (
        <div key={key}>
          <strong>{key}:</strong> {value}
        </div>
      ))}
    </div>
  );

  const handleExpandClick = (profile) => {
    setExpandedProfiles((prevState) =>
      prevState.includes(profile.profile_id)
        ? prevState.filter((id) => id !== profile.profile_id)
        : [...prevState, profile.profile_id]
    );
  };

  const handleTagChange = (checked, profileId) => {
    setEnabledProfiles((prevState) =>
      checked
        ? [...prevState, profileId]
        : prevState.filter((id) => id !== profileId)
    );
  };

  const getColSpan = () => {
    if (componentWidth < 1200) {
      return 24;
    } else {
      return 6;
    }
  };

  useEffect(() => {
    setExpandCard(true);
  }, [isSinglePassExtractLoading]);

  useEffect(() => {
    if (singlePassExtractMode) {
      setExpandedProfiles([]);
    }
  }, [singlePassExtractMode]);

  useEffect(() => {
    getAdapterInfo();
  }, [llmProfiles, selectedLlmProfileId, enabledProfiles]);
  return (
    <Card className="prompt-card">
      <div className="prompt-card-div prompt-card-bg-col1 prompt-card-rad">
        <Space direction="vertical" className="width-100" ref={divRef}>
          <Header
            promptDetails={promptDetails}
            promptKey={promptKey}
            setPromptKey={setPromptKey}
            progressMsg={progressMsg}
            handleRun={handleRun}
            handleChange={handleChange}
            handleDelete={handleDelete}
            updateStatus={updateStatus}
            updatePlaceHolder={updatePlaceHolder}
            isCoverageLoading={isCoverageLoading}
            isEditingTitle={isEditingTitle}
            setIsEditingTitle={setIsEditingTitle}
            enableEdit={enableEdit}
            expandCard={expandCard}
            setExpandCard={setExpandCard}
            enabledProfiles={enabledProfiles}
          />
        </Space>
      </div>
      <Collapse
        className="prompt-card-collapse prompt-card-bg-col1"
        ghost
        activeKey={expandCard && "1"}
      >
        <Collapse.Panel key={"1"} showArrow={false}>
          <div className="prompt-card-div-body">
            <EditableText
              isEditing={isEditingPrompt}
              setIsEditing={setIsEditingPrompt}
              text={promptText}
              setText={setPromptText}
              promptId={promptDetails?.prompt_id}
              defaultText={promptDetails.prompt}
              handleChange={handleChange}
              isTextarea={true}
              placeHolder={updatePlaceHolder}
            />
          </div>
          <>
            <Divider className="prompt-card-divider" />
            <Space
              direction="vertical"
              className={`prompt-card-comp-layout ${
                !(isRunLoading || result?.output || result?.output === 0) &&
                "prompt-card-comp-layout-border"
              }`}
            >
              <div className="prompt-card-llm-profiles">
                <Space direction="horizontal">
                  {EvalBtn && !singlePassExtractMode && (
                    <EvalBtn
                      btnText={promptDetails?.evaluate ? "On" : "Off"}
                      promptId={promptDetails.prompt_id}
                      setOpenEval={setOpenEval}
                    />
                  )}
                  <Button
                    size="small"
                    type="link"
                    className="display-flex-align-center prompt-card-action-button"
                    onClick={() => setOpenOutputForDoc(true)}
                  >
                    <Space>
                      {isCoverageLoading ? (
                        <SpinnerLoader size="small" />
                      ) : (
                        <SearchOutlined className="font-size-12" />
                      )}
                      <Typography.Link className="font-size-12">
                        Coverage:{" "}
                        {coverage[
                          `${promptDetails.prompt_id}_${selectedLlmProfileId}`
                        ]?.docs_covered.length || 0}{" "}
                        of {listOfDocs?.length || 0} docs
                      </Typography.Link>
                    </Space>
                  </Button>
                </Space>
                <Space>
                  <Select
                    className="prompt-card-select-type"
                    size="small"
                    placeholder="Enforce Type"
                    optionFilterProp="children"
                    options={enforceTypeList}
                    value={promptDetails?.enforce_type || null}
                    disabled={
                      disableLlmOrDocChange.includes(
                        promptDetails?.prompt_id
                      ) ||
                      isSinglePassExtractLoading ||
                      indexDocs.includes(selectedDoc?.document_id)
                    }
                    onChange={(value) => handleTypeChange(value)}
                  />
                </Space>
              </div>
              {EvalMetrics && <EvalMetrics result={result} />}
            </Space>
          </>
          <Row>
            <AnimatePresence>
              {!singlePassExtractMode &&
                llmProfileDetails.map((profile, index) => {
                  const checked = enabledProfiles.includes(profile.profile_id);
                  const tokenUsageId =
                    promptDetails?.prompt_id +
                    "__" +
                    selectedDoc?.document_id +
                    "__" +
                    profile.profile_id;
                  return (
                    <motion.div
                      key={profile.profile_id}
                      initial={{ x: 0 }}
                      animate={{
                        x:
                          profile?.profile_id === selectedLlmProfileId &&
                          index !== 0
                            ? -10
                            : 0,
                      }}
                      transition={{ duration: 0.5, ease: "linear" }}
                      className="prompt-card-llm"
                    >
                      <Col
                        key={profile?.profile_id}
                        className="prompt-card-llm-container"
                        xs={{ span: getColSpan() }}
                      >
                        <Divider className="prompt-card-divider" />
                        <Space
                          direction="vertical"
                          className="prompt-card-llm-layout"
                        >
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
                              {profile?.conf.llm}
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
                              Cost: $0.0004
                            </Typography.Text>
                          </div>
                          <div className="prompt-info">
                            <CheckableTag
                              checked={enabledProfiles.includes(
                                profile.profile_id
                              )}
                              onChange={(checked) =>
                                handleTagChange(checked, profile.profile_id)
                              }
                              style={{
                                backgroundColor: checked
                                  ? "#F6FFED"
                                  : "#00000005",
                                borderColor: checked ? "#B7EB8F" : "#00000026",
                                color: checked ? "#52C41A" : "#000",
                              }}
                            >
                              {enabledProfiles.includes(profile.profile_id) ? (
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
                              <DatabaseOutlined
                                onClick={() => {
                                  setIsIndexOpen(true);
                                  setOpenIndexProfile(profile?.profile_id);
                                }}
                                className="prompt-card-actions-head"
                              />
                              <Radio
                                checked={
                                  profile?.profile_id === selectedLlmProfileId
                                }
                                onChange={() =>
                                  handleSelectDefaultLLM(profile?.profile_id)
                                }
                              >
                                Default
                              </Radio>
                            </div>
                          </div>
                        </Space>
                        <>
                          <Divider className="prompt-card-divider" />
                          <div
                            className={`prompt-card-result prompt-card-div ${
                              expandedProfiles.includes(profile.profile_id) &&
                              "prompt-profile-run-expanded"
                            }`}
                          >
                            {isRunLoading[
                              `${selectedDoc?.document_id}_${profile?.profile_id}`
                            ] ? (
                              <Spin
                                indicator={<SpinnerLoader size="small" />}
                              />
                            ) : (
                              <Typography.Paragraph className="prompt-card-res font-size-12">
                                <div
                                  className={
                                    expandedProfiles.includes(
                                      profile.profile_id
                                    )
                                      ? "expanded-output"
                                      : "collapsed-output"
                                  }
                                >
                                  {displayPromptResult(
                                    result.find(
                                      (r) =>
                                        r?.profileManager ===
                                        profile?.profile_id
                                    )?.output,
                                    true
                                  )}
                                </div>
                              </Typography.Paragraph>
                            )}
                            <div className="prompt-profile-run">
                              <>
                                <Tooltip title="Run">
                                  <Button
                                    size="small"
                                    type="text"
                                    className="prompt-card-action-button"
                                    onClick={() =>
                                      handleRun(profile?.profile_id, false)
                                    }
                                    disabled={
                                      isRunLoading[
                                        `${selectedDoc?.document_id}_${profile?.profile_id}`
                                      ]
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
                                    onClick={() =>
                                      handleRun(profile?.profile_id, true)
                                    }
                                    disabled={
                                      isRunLoading[
                                        `${selectedDoc?.document_id}_${profile?.profile_id}`
                                      ]
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
                        </>
                      </Col>
                    </motion.div>
                  );
                })}
            </AnimatePresence>
            {singlePassExtractMode &&
              (() => {
                const [firstResult] = result || [];
                if (firstResult?.output || firstResult?.output === 0) {
                  return (
                    <>
                      <Divider className="prompt-card-divider" />
                      <div
                        className={`prompt-card-result prompt-card-div ${
                          expandedProfiles.includes(
                            firstResult.profileManager
                          ) && "prompt-profile-run-expanded"
                        }`}
                      >
                        {isSinglePassExtractLoading ? (
                          <Spin indicator={<SpinnerLoader size="small" />} />
                        ) : (
                          <Typography.Paragraph className="prompt-card-res font-size-12">
                            <div
                              className={
                                expandedProfiles.includes(
                                  firstResult.profileManager
                                )
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
                return null;
              })()}
          </Row>
        </Collapse.Panel>
      </Collapse>
      <OutputForIndex
        llmProfileId={openIndexProfile}
        isIndexOpen={isIndexOpen}
        setIsIndexOpen={setIsIndexOpen}
      />
    </Card>
  );
}

PromptCardItems.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array,
  isRunLoading: PropTypes.object,
  promptKey: PropTypes.text,
  setPromptKey: PropTypes.func.isRequired,
  promptText: PropTypes.text,
  setPromptText: PropTypes.func.isRequired,
  result: PropTypes.object.isRequired,
  coverage: PropTypes.number.isRequired,
  progressMsg: PropTypes.object.isRequired,
  handleRun: PropTypes.func.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleSelectDefaultLLM: PropTypes.func.isRequired,
  handleTypeChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  updatePlaceHolder: PropTypes.string,
  isCoverageLoading: PropTypes.bool.isRequired,
  setOpenEval: PropTypes.func.isRequired,
  setOpenOutputForDoc: PropTypes.func.isRequired,
  selectedLlmProfileId: PropTypes.string,
  timers: PropTypes.object.isRequired,
};

export { PromptCardItems };
