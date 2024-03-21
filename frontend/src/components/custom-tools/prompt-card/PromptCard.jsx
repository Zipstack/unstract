import {
  ArrowDownOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  LeftOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  RightOutlined,
  SearchOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import debounce from "lodash/debounce";
import PropTypes from "prop-types";
import { useCallback, useEffect, useRef, useState } from "react";

import { AssertionIcon } from "../../../assets";
import {
  displayPromptResult,
  promptStudioUpdateStatus,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EditableText } from "../editable-text/EditableText";
import { OutputForDocModal } from "../output-for-doc-modal/OutputForDocModal";
import "./PromptCard.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";

let EvalBtn = null;
let EvalMetrics = null;
let EvalModal = null;
let getEvalMetrics = (param1, param2, param3) => {
  return [];
};
try {
  EvalBtn = require("../../../plugins/eval-btn/EvalBtn").EvalBtn;
  EvalMetrics =
    require("../../../plugins/eval-metrics/EvalMetrics").EvalMetrics;
  EvalModal = require("../../../plugins/eval-modal/EvalModal").EvalModal;
  getEvalMetrics =
    require("../../../plugins/eval-helper/EvalHelper").getEvalMetrics;
} catch {
  // The components will remain null of it is not available
}

function PromptCard({
  promptDetails,
  handleChange,
  handleDelete,
  updateStatus,
  updatePlaceHolder,
}) {
  const [enforceTypeList, setEnforceTypeList] = useState([]);
  const [page, setPage] = useState(0);
  const [isRunLoading, setIsRunLoading] = useState(false);
  const [displayAssertion, setDisplayAssertion] = useState(false);
  const [openEval, setOpenEval] = useState(false);
  const [promptKey, setPromptKey] = useState("");
  const [promptText, setPromptText] = useState("");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [selectedLlmProfileId, setSelectedLlmProfileId] = useState(null);
  const [result, setResult] = useState({
    promptOutputId: null,
    output: "",
  });
  const [coverage, setCoverage] = useState(0);
  const [coverageTotal, setCoverageTotal] = useState(0);
  const [isCoverageLoading, setIsCoverageLoading] = useState(false);
  const [openOutputForDoc, setOpenOutputForDoc] = useState(false);
  const [progressMsg, setProgressMsg] = useState({});
  const [docOutputs, setDocOutputs] = useState({});
  const divRef = useRef(null);
  const {
    getDropdownItems,
    llmProfiles,
    selectedDoc,
    listOfDocs,
    updateCustomTool,
    details,
    disableLlmOrDocChange,
    indexDocs,
    summarizeIndexStatus,
    singlePassExtractMode,
    isSinglePassExtractLoading,
  } = useCustomToolStore();
  const { messages } = useSocketCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    // Find the latest message that matches the criteria
    const msg = [...messages]
      .reverse()
      .find(
        (item) =>
          (item?.component?.prompt_id === promptDetails?.prompt_id ||
            item?.component?.prompt_key === promptKey) &&
          (item?.level === "INFO" || item?.level === "ERROR")
      );

    // If no matching message is found, return early
    if (!msg) {
      return;
    }

    // Set the progress message state with the found message
    setProgressMsg({
      message: msg?.message || "",
      level: msg?.level || "INFO",
    });
  }, [messages]);

  useEffect(() => {
    if (promptDetails?.is_assert) {
      setDisplayAssertion(true);
    }
    const outputTypeData = getDropdownItems("output_type");
    const dropdownList1 = Object.keys(outputTypeData).map((item) => {
      return { value: outputTypeData[item] };
    });
    setEnforceTypeList(dropdownList1);
  }, []);

  useEffect(() => {
    setSelectedLlmProfileId(promptDetails?.profile_manager || null);
  }, [promptDetails]);

  useEffect(() => {
    if (isSinglePassExtractLoading) {
      return;
    }

    handleGetOutput();
    handleGetCoverage();
  }, [
    selectedLlmProfileId,
    selectedDoc,
    listOfDocs,
    singlePassExtractMode,
    isSinglePassExtractLoading,
  ]);

  useEffect(() => {
    let listOfIds = [...disableLlmOrDocChange];
    const promptId = promptDetails?.prompt_id;
    const isIncluded = listOfIds.includes(promptId);

    if (
      (isIncluded && isCoverageLoading) ||
      (!isIncluded && !isCoverageLoading)
    ) {
      return;
    }

    if (isIncluded && !isCoverageLoading) {
      listOfIds = listOfIds.filter((item) => item !== promptId);
    }

    if (!isIncluded && isCoverageLoading) {
      listOfIds.push(promptId);
    }
    updateCustomTool({ disableLlmOrDocChange: listOfIds });
  }, [isCoverageLoading]);

  useEffect(() => {
    if (page < 1) {
      return;
    }
    const llmProfile = llmProfiles[page - 1];
    if (llmProfile?.profile_id !== promptDetails?.profile_id) {
      handleChange(
        llmProfile?.profile_id,
        promptDetails?.prompt_id,
        "profile_manager"
      );
    }
  }, [page]);

  useEffect(() => {
    if (displayAssertion !== promptDetails?.is_assert) {
      handleChange(
        displayAssertion,
        promptDetails?.prompt_id,
        "is_assert",
        true
      );
    }
  }, [displayAssertion]);

  useEffect(() => {
    if (isCoverageLoading && coverageTotal === listOfDocs?.length) {
      setIsCoverageLoading(false);
      setCoverageTotal(0);
    }
  }, [coverageTotal]);

  const onSearchDebounce = useCallback(
    debounce((event) => {
      handleChange(event, promptDetails?.prompt_id, false, true);
    }, 1000),
    []
  );

  useEffect(() => {
    const isProfilePresent = llmProfiles.some(
      (profile) => profile.profile_id === selectedLlmProfileId
    );

    // If selectedLlmProfileId is not present, set it to null
    if (!isProfilePresent) {
      setSelectedLlmProfileId(null);
    }

    const llmProfileId = promptDetails?.profile_manager;
    if (!llmProfileId) {
      setPage(0);
      return;
    }
    const index = llmProfiles.findIndex(
      (item) => item?.profile_id === llmProfileId
    );
    setPage(index + 1);
  }, [llmProfiles]);

  const handlePageLeft = () => {
    if (page <= 1) {
      return;
    }

    const newPage = page - 1;
    setPage(newPage);
  };

  const handlePageRight = () => {
    if (page >= llmProfiles?.length) {
      return;
    }

    const newPage = page + 1;
    setPage(newPage);
  };

  const handleTypeChange = (value) => {
    handleChange(value, promptDetails?.prompt_id, "enforce_type", true).then(
      () => {
        handleRun();
      }
    );
  };

  const handleDocOutputs = (docId, isLoading, output) => {
    setDocOutputs((prev) => {
      const updatedDocOutputs = { ...prev };
      // Update the entry for the provided docId with isLoading and output
      updatedDocOutputs[docId] = {
        isLoading,
        output,
      };
      return updatedDocOutputs;
    });
  };

  // Generate the result for the currently selected document
  const handleRun = () => {
    if (!promptDetails?.profile_manager?.length) {
      setAlertDetails({
        type: "error",
        content: "LLM Profile is not selected",
      });
      return;
    }

    if (!selectedDoc) {
      setAlertDetails({
        type: "error",
        content: "Document not selected",
      });
      return;
    }

    if (!promptKey) {
      setAlertDetails({
        type: "error",
        content: "Prompt key cannot be empty",
      });
      return;
    }

    if (!promptText) {
      setAlertDetails({
        type: "error",
        content: "Prompt cannot be empty",
      });
      return;
    }

    setIsRunLoading(true);
    setIsCoverageLoading(true);
    setCoverage(0);
    setCoverageTotal(0);

    const docId = selectedDoc?.document_id;
    const isSummaryIndexed = [...summarizeIndexStatus].find(
      (item) => item?.docId === docId && item?.isIndexed === true
    );

    if (
      !isSummaryIndexed &&
      details?.summarize_as_source &&
      details?.summarize_llm_profile
    ) {
      // Summary needs to be indexed before running the prompt
      handleStepsAfterRunCompletion();
      setAlertDetails({
        type: "error",
        content: `Summary needs to be indexed before running the prompt - ${selectedDoc?.document_name}.`,
      });
      return;
    }

    handleDocOutputs(docId, true, null);
    handleRunApiRequest(docId)
      .then((res) => {
        const data = res?.data;
        const value = data[promptDetails?.prompt_key];
        if (value || value === 0) {
          setCoverage((prev) => prev + 1);
        }
        handleDocOutputs(docId, false, value);
        handleGetOutput();
      })
      .catch((err) => {
        setIsRunLoading(false);
        handleDocOutputs(docId, false, null);
        setAlertDetails(
          handleException(err, `Failed to generate output for ${docId}`)
        );
      })
      .finally(() => {
        handleStepsAfterRunCompletion();
      });
  };

  const handleStepsAfterRunCompletion = () => {
    setCoverageTotal(1);
    handleCoverage();
  };

  // Get the coverage for all the documents except the one that's currently selected
  const handleCoverage = () => {
    const listOfDocsToProcess = [...listOfDocs].filter(
      (item) => item?.document_id !== selectedDoc?.document_id
    );

    if (listOfDocsToProcess?.length === 0) {
      setIsCoverageLoading(false);
      return;
    }

    let totalCoverageValue = 1;
    listOfDocsToProcess.forEach((item) => {
      const docId = item?.document_id;
      const isSummaryIndexed = [...summarizeIndexStatus].find(
        (indexStatus) =>
          indexStatus?.docId === docId && indexStatus?.isIndexed === true
      );

      if (
        !isSummaryIndexed &&
        details?.summarize_as_source &&
        details?.summarize_llm_profile
      ) {
        // Summary needs to be indexed before running the prompt
        totalCoverageValue++;
        setCoverageTotal(totalCoverageValue);
        setAlertDetails({
          type: "error",
          content: `Summary needs to be indexed before running the prompt - ${item?.document_name}.`,
        });
        return;
      }

      handleDocOutputs(docId, true, null);
      handleRunApiRequest(docId)
        .then((res) => {
          const data = res?.data;
          const outputValue = data[promptDetails?.prompt_key];
          if (outputValue || outputValue === 0) {
            setCoverage((prev) => prev + 1);
          }
          handleDocOutputs(docId, false, outputValue);
        })
        .catch((err) => {
          handleDocOutputs(docId, false, null);
          setAlertDetails(
            handleException(err, `Failed to generate output for ${docId}`)
          );
        })
        .finally(() => {
          totalCoverageValue++;
          setCoverageTotal(totalCoverageValue);
        });
    });
  };

  const handleRunApiRequest = async (docId) => {
    const promptId = promptDetails?.prompt_id;

    const body = {
      document_id: docId,
      id: promptId,
      tool_id: details?.tool_id,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/fetch_response/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const handleGetOutput = () => {
    if (!selectedDoc || !selectedLlmProfileId) {
      setResult({
        promptOutputId: null,
        output: "",
      });
      return;
    }

    setIsRunLoading(true);
    handleOutputApiRequest(true)
      .then((res) => {
        const data = res?.data;
        if (!data || data?.length === 0) {
          setResult({
            promptOutputId: null,
            output: "",
          });
          return;
        }

        const outputResult = data[0];
        setResult({
          promptOutputId: outputResult?.prompt_output_id,
          output: outputResult?.output,
          evalMetrics: getEvalMetrics(
            promptDetails?.evaluate,
            promptDetails?.prompt_key,
            outputResult?.eval_metrics || []
          ),
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate the result"));
      })
      .finally(() => {
        setIsRunLoading(false);
      });
  };

  const handleGetCoverage = () => {
    if (!selectedLlmProfileId) {
      return;
    }

    setCoverage(0);
    handleOutputApiRequest(false)
      .then((res) => {
        const data = res?.data;
        handleGetCoverageData(data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate the result"));
      });
  };

  const handleOutputApiRequest = async (isOutput) => {
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptDetails?.prompt_id}&profile_manager=${selectedLlmProfileId}&is_single_pass_extract_mode_active=${singlePassExtractMode}`;

    if (isOutput) {
      url += `&document_manager=${selectedDoc?.document_id}`;
    }

    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => {
        throw err;
      });
  };

  const handleGetCoverageData = (data) => {
    const coverageValue = data.reduce((acc, item) => {
      if (item?.output || item?.output === 0) {
        return acc + 1;
      } else {
        return acc;
      }
    }, 0);
    setCoverage(coverageValue);
  };

  const enableEdit = (event) => {
    event.stopPropagation();
    setIsEditingTitle(true);
    setIsEditingPrompt(true);
  };

  return (
    <>
      <Card className="prompt-card">
        <Collapse
          className="assertion-comp"
          ghost
          activeKey={displayAssertion ? "1" : null}
        >
          <Collapse.Panel key={"1"} showArrow={false}>
            <Row className="prompt-card-div">
              <Col span={8} className="assert-p-r-4">
                <Typography.Text strong className="font-size-12">
                  Missing Context Prompt
                </Typography.Text>
                <div className="prompt-card-gap" />
                <Input.TextArea
                  rows={2}
                  defaultValue={promptDetails?.assert_prompt}
                  name="assert_prompt"
                  onChange={onSearchDebounce}
                  disabled={
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id) ||
                    isSinglePassExtractLoading ||
                    indexDocs.includes(selectedDoc?.document_id)
                  }
                />
              </Col>
              <Col span={8} className="assert-p-l-4 assert-p-r-4">
                <Typography.Text className="font-size-12" strong>
                  False
                </Typography.Text>
                <div className="prompt-card-gap" />
                <Input.TextArea
                  rows={2}
                  defaultValue={promptDetails?.assertion_failure_prompt}
                  name="assertion_failure_prompt"
                  onChange={onSearchDebounce}
                  disabled={
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id) ||
                    isSinglePassExtractLoading ||
                    indexDocs.includes(selectedDoc?.document_id)
                  }
                />
              </Col>
              <Col span={8} className="assert-p-l-4">
                <Typography.Text className="font-size-12" strong>
                  True
                </Typography.Text>
                <div className="prompt-card-gap" />
                <SpaceWrapper>
                  <Typography.Text className="font-size-12">
                    The below prompt will be executed.
                  </Typography.Text>
                  <ArrowDownOutlined />
                </SpaceWrapper>
              </Col>
            </Row>
          </Collapse.Panel>
        </Collapse>
        <>
          {displayAssertion && <Divider className="prompt-card-divider" />}
          <div
            className={`prompt-card-div prompt-card-bg-col1 ${
              displayAssertion ? "" : "prompt-card-rad"
            }`}
          >
            <Space direction="vertical" className="width-100" ref={divRef}>
              <Row>
                <Col span={12}>
                  <EditableText
                    isEditing={isEditingTitle}
                    setIsEditing={setIsEditingTitle}
                    text={promptKey}
                    setText={setPromptKey}
                    promptId={promptDetails?.prompt_id}
                    defaultText={promptDetails?.prompt_key}
                    handleChange={handleChange}
                    placeHolder={updatePlaceHolder}
                  />
                </Col>
                <Col span={12} className="display-flex-right">
                  {progressMsg?.message && (
                    <Tag
                      icon={isCoverageLoading && <LoadingOutlined spin />}
                      color={
                        progressMsg?.level === "ERROR" ? "error" : "processing"
                      }
                      className="display-flex-align-center"
                    >
                      {progressMsg?.message}
                    </Tag>
                  )}
                  {updateStatus?.promptId === promptDetails?.prompt_id && (
                    <>
                      {updateStatus?.status ===
                        promptStudioUpdateStatus.isUpdating && (
                        <Tag
                          icon={<SyncOutlined spin />}
                          color="processing"
                          className="display-flex-align-center"
                        >
                          Updating
                        </Tag>
                      )}
                      {updateStatus?.status ===
                        promptStudioUpdateStatus.done && (
                        <Tag
                          icon={<CheckCircleOutlined />}
                          color="success"
                          className="display-flex-align-center"
                        >
                          Done
                        </Tag>
                      )}
                      {updateStatus?.status ===
                        promptStudioUpdateStatus.validationError && (
                        <Tag
                          icon={<CheckCircleOutlined />}
                          color="error"
                          className="display-flex-align-center"
                        >
                          Invalid JSON Key
                        </Tag>
                      )}
                    </>
                  )}
                  <Tooltip title="Edit">
                    <Button
                      size="small"
                      type="text"
                      className="display-flex-align-center"
                      onClick={enableEdit}
                      disabled={
                        disableLlmOrDocChange.includes(
                          promptDetails?.prompt_id
                        ) ||
                        isSinglePassExtractLoading ||
                        indexDocs.includes(selectedDoc?.document_id)
                      }
                    >
                      <EditOutlined className="prompt-card-actions-head" />
                    </Button>
                  </Tooltip>
                  <Tooltip title="Assertion">
                    <Button
                      size="small"
                      type="text"
                      className="display-flex-align-center"
                      onClick={() => setDisplayAssertion(!displayAssertion)}
                      disabled={true}
                    >
                      <AssertionIcon className="prompt-card-actions-head" />
                    </Button>
                  </Tooltip>
                  {!singlePassExtractMode && (
                    <Tooltip title="Run">
                      <Button
                        size="small"
                        type="text"
                        onClick={handleRun}
                        disabled={
                          (updateStatus?.promptId ===
                            promptDetails?.prompt_id &&
                            updateStatus?.status ===
                              promptStudioUpdateStatus.isUpdating) ||
                          disableLlmOrDocChange.includes(
                            promptDetails?.prompt_id
                          ) ||
                          indexDocs.includes(selectedDoc?.document_id)
                        }
                      >
                        <PlayCircleOutlined className="prompt-card-actions-head" />
                      </Button>
                    </Tooltip>
                  )}
                  <ConfirmModal
                    handleConfirm={() => handleDelete(promptDetails?.prompt_id)}
                    content="The prompt will be permanently deleted."
                  >
                    <Tooltip title="Delete">
                      <Button
                        size="small"
                        type="text"
                        disabled={
                          disableLlmOrDocChange.includes(
                            promptDetails?.prompt_id
                          ) ||
                          isSinglePassExtractLoading ||
                          indexDocs.includes(selectedDoc?.document_id)
                        }
                      >
                        <DeleteOutlined className="prompt-card-actions-head" />
                      </Button>
                    </Tooltip>
                  </ConfirmModal>
                </Col>
              </Row>
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
            </Space>
          </div>
        </>
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
                {EvalBtn && (
                  <EvalBtn
                    btnText={promptDetails?.evaluate ? "On" : "Off"}
                    promptId={promptDetails.prompt_id}
                    setOpenEval={setOpenEval}
                  />
                )}
                <Button
                  size="small"
                  type="link"
                  className="display-flex-align-center"
                  onClick={() => setOpenOutputForDoc(true)}
                >
                  <Space>
                    {isCoverageLoading ? (
                      <SpinnerLoader size="small" />
                    ) : (
                      <SearchOutlined className="font-size-12" />
                    )}
                    <Typography.Link className="font-size-12">
                      Coverage: {coverage} of {listOfDocs?.length || 0} docs
                    </Typography.Link>
                  </Space>
                </Button>
              </Space>
              <div>
                <Select
                  className="prompt-card-select-type"
                  size="small"
                  placeholder="Enforce Type"
                  optionFilterProp="children"
                  options={enforceTypeList}
                  value={promptDetails?.enforce_type || null}
                  disabled={
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id) ||
                    isSinglePassExtractLoading ||
                    indexDocs.includes(selectedDoc?.document_id)
                  }
                  onChange={(value) => handleTypeChange(value)}
                />
              </div>
            </div>
            <div className="prompt-card-llm-profiles">
              {llmProfiles?.length > 0 &&
              promptDetails?.profile_manager?.length > 0 &&
              selectedLlmProfileId ? (
                <div>
                  {llmProfiles
                    .filter(
                      (profile) => profile.profile_id === selectedLlmProfileId
                    )
                    .map((profile, index) => (
                      <div key={index}>
                        <Tag>{profile.llm}</Tag>
                        <Tag>{profile.vector_store}</Tag>
                        <Tag>{profile.embedding_model}</Tag>
                        <Tag>{profile.x2text}</Tag>
                        <Tag>{`${profile.chunk_size}/${profile.chunk_overlap}/${profile.retrieval_strategy}/${profile.similarity_top_k}/${profile.section}`}</Tag>
                      </div>
                    ))}
                </div>
              ) : (
                <div>
                  <Typography.Text className="font-size-12">
                    No LLM Profile Selected
                  </Typography.Text>
                </div>
              )}
              <div className="display-flex-right prompt-card-paginate-div">
                <Button
                  type="text"
                  size="small"
                  disabled={
                    page <= 1 ||
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id) ||
                    isSinglePassExtractLoading ||
                    indexDocs.includes(selectedDoc?.document_id)
                  }
                  onClick={handlePageLeft}
                >
                  <LeftOutlined className="prompt-card-paginate" />
                </Button>
                <Button
                  type="text"
                  size="small"
                  disabled={
                    page >= llmProfiles?.length ||
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id) ||
                    isSinglePassExtractLoading ||
                    indexDocs.includes(selectedDoc?.document_id)
                  }
                  onClick={handlePageRight}
                >
                  <RightOutlined className="prompt-card-paginate" />
                </Button>
              </div>
            </div>
            {EvalMetrics && <EvalMetrics result={result} />}
          </Space>
        </>
        {(isRunLoading || result?.output || result?.output === 0) && (
          <>
            <Divider className="prompt-card-divider" />
            <div className="prompt-card-result prompt-card-div">
              {isRunLoading ? (
                <Spin indicator={<SpinnerLoader size="small" />} />
              ) : (
                <Typography.Paragraph className="prompt-card-res font-size-12">
                  <div>{displayPromptResult(result?.output, true)}</div>
                </Typography.Paragraph>
              )}
            </div>
          </>
        )}
      </Card>
      {EvalModal && (
        <EvalModal
          open={openEval}
          setOpen={setOpenEval}
          promptDetails={promptDetails}
          handleChange={handleChange}
        />
      )}
      <OutputForDocModal
        open={openOutputForDoc}
        setOpen={setOpenOutputForDoc}
        promptId={promptDetails?.prompt_id}
        promptKey={promptDetails?.prompt_key}
        profileManagerId={promptDetails?.profile_manager}
        docOutputs={docOutputs}
      />
    </>
  );
}

PromptCard.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
  updatePlaceHolder: PropTypes.string,
};

export { PromptCard };
