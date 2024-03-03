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
  handleException,
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

let EvalBtn = null;
let EvalMetrics = null;
let EvalModal = null;

try {
  EvalBtn = require("../../../plugins/eval-btn/EvalBtn").EvalBtn;
  EvalMetrics =
    require("../../../plugins/eval-metrics/EvalMetrics").EvalMetrics;
  EvalModal = require("../../../plugins/eval-modal/EvalModal").EvalModal;
} catch {
  console.log("Component failed to render");
}

function PromptCard({
  promptDetails,
  handleChange,
  handleDelete,
  updateStatus,
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
    evalMetrics: [],
  });
  const [outputIds, setOutputIds] = useState([]);
  const [coverage, setCoverage] = useState(0);
  const [coverageTotal, setCoverageTotal] = useState(0);
  const [isCoverageLoading, setIsCoverageLoading] = useState(false);
  const [openOutputForDoc, setOpenOutputForDoc] = useState(false);
  const divRef = useRef(null);
  const {
    getDropdownItems,
    llmProfiles,
    selectedDoc,
    listOfDocs,
    updateCustomTool,
    details,
    disableLlmOrDocChange,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    if (promptDetails?.is_assert) {
      setDisplayAssertion(true);
    }
    const outputTypeData = getDropdownItems("output_type");
    const dropdownList1 = Object.keys(outputTypeData).map((item) => {
      return { value: outputTypeData[item] };
    });
    setEnforceTypeList(dropdownList1);

    const llmProfileId = promptDetails?.profile_manager;
    if (!llmProfileId) {
      setPage(0);
      return;
    }
    const index = llmProfiles.findIndex(
      (item) => item?.profile_id === llmProfileId
    );
    setPage(index + 1);
  }, []);

  useEffect(() => {
    setSelectedLlmProfileId(promptDetails?.profile_manager || null);
  }, [promptDetails]);

  useEffect(() => {
    handleGetOutput();
    handleGetCoverage();
  }, [selectedLlmProfileId, selectedDoc, listOfDocs]);

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
    }
  }, [coverageTotal]);

  const onSearchDebounce = useCallback(
    debounce((event) => {
      handleChange(event, promptDetails?.prompt_id, false, true);
    }, 1000),
    []
  );

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

  const sortEvalMetricsByType = (metrics) => {
    const sieve = {};
    for (const metric of metrics) {
      if (!sieve[metric.type]) {
        sieve[metric.type] = [metric];
      } else {
        sieve[metric.type].push(metric);
      }
    }

    let sortedMetrics = [];
    for (const type of Object.keys(sieve)) {
      sortedMetrics = sortedMetrics.concat(sieve[type]);
    }

    return sortedMetrics;
  };

  const handleTypeChange = (value) => {
    handleChange(value, promptDetails?.prompt_id, "enforce_type", true).then(
      () => {
        handleRun();
      }
    );
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

    let method = "POST";
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/`;
    if (result?.promptOutputId) {
      method = "PATCH";
      url += `${result?.promptOutputId}/`;
    }
    handleRunApiRequest(selectedDoc)
      .then((res) => {
        const data = res?.data;
        const value = data[promptDetails?.prompt_key];
        if (value !== null && String(value)?.length > 0) {
          setCoverage((prev) => prev + 1);
        }

        // Handle Eval
        let evalMetrics = [];
        if (promptDetails?.evaluate) {
          evalMetrics = data[`${promptDetails?.prompt_key}__evaluation`] || [];
        }
        handleUpdateOutput(value, selectedDoc, evalMetrics, method, url);
      })
      .catch((err) => {
        handleUpdateOutput(null, selectedDoc, [], method, url);
        setAlertDetails(
          handleException(err, `Failed to generate output for ${selectedDoc}`)
        );
      })
      .finally(() => {
        setIsRunLoading(false);
        setCoverageTotal((prev) => prev + 1);
        handleCoverage();
      });
  };

  // Get the coverage for all the documents except the one that's currently selected
  const handleCoverage = () => {
    const listOfDocsToProcess = [...listOfDocs].filter(
      (item) => item !== selectedDoc
    );

    if (listOfDocsToProcess?.length === 0) {
      setIsCoverageLoading(false);
      return;
    }

    listOfDocsToProcess.forEach((item) => {
      let method = "POST";
      let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/`;
      const outputId = outputIds.find((output) => output?.docName === item);
      if (outputId?.promptOutputId?.length) {
        method = "PATCH";
        url += `${outputId?.promptOutputId}/`;
      }
      handleRunApiRequest(item)
        .then((res) => {
          const data = res?.data;
          const outputValue = data[promptDetails?.prompt_key];
          if (outputValue !== null && String(outputValue)?.length > 0) {
            setCoverage((prev) => prev + 1);
          }

          // Handle Eval
          let evalMetrics = [];
          if (promptDetails?.evaluate) {
            evalMetrics =
              data[`${promptDetails?.prompt_key}__evaluation`] || [];
          }
          handleUpdateOutput(outputValue, item, evalMetrics, method, url);
        })
        .catch((err) => {
          handleUpdateOutput(null, item, [], method, url);
          setAlertDetails(
            handleException(err, `Failed to generate output for ${item}`)
          );
        })
        .finally(() => {
          setCoverageTotal((prev) => prev + 1);
        });
    });
  };

  const handleRunApiRequest = async (doc) => {
    const promptId = promptDetails?.prompt_id;

    const body = {
      file_name: doc,
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

  const handleUpdateOutput = (
    outputValue,
    docName,
    evalMetrics,
    method,
    url
  ) => {
    let output = outputValue;
    if (output !== null && typeof output !== "string") {
      output = JSON.stringify(output);
    }
    const body = {
      output: output !== null ? output : null,
      tool_id: details?.tool_id,
      prompt_id: promptDetails?.prompt_id,
      profile_manager: promptDetails?.profile_manager,
      doc_name: docName,
      eval_metrics: evalMetrics,
    };

    const requestOptions = {
      method,
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const promptOutputId = data?.prompt_output_id || null;
        if (docName === selectedDoc) {
          setResult({
            promptOutputId: promptOutputId,
            output: data?.output,
            evalMetrics: sortEvalMetricsByType(data?.eval_metrics || []),
          });
        }

        const isOutputIdAvailable = outputIds.find(
          (item) => item?.promptOutputId === promptOutputId
        );
        if (!isOutputIdAvailable) {
          const listOfOutputIds = [...outputIds];
          listOfOutputIds.push({ promptOutputId, docName });
          setOutputIds(listOfOutputIds);
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to persist the result"));
      });
  };

  const handleGetOutput = () => {
    if (!selectedDoc || !selectedLlmProfileId) {
      setResult({
        promptOutputId: null,
        output: "",
        evalMetrics: [],
      });
      return;
    }

    setIsRunLoading(true);
    handleOutputApiRequest(true)
      .then((data) => {
        if (!data || data?.length === 0) {
          setResult({
            promptOutputId: null,
            output: "",
            evalMetrics: [],
          });
          return;
        }

        const outputResult = data[0];
        setResult({
          promptOutputId: outputResult?.prompt_output_id,
          output: outputResult?.output,
          evalMetrics: sortEvalMetricsByType(outputResult?.eval_metrics || []),
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate the output"));
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
    handleOutputApiRequest()
      .then((data) => {
        handleGetCoverageData(data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate result"));
      });
  };

  const handleOutputApiRequest = async (isOutput) => {
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptDetails?.prompt_id}&profile_manager=${selectedLlmProfileId}`;

    if (isOutput) {
      url += `&doc_name=${selectedDoc}`;
    }
    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    return axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        data.sort((a, b) => {
          return new Date(b.modified_at) - new Date(a.modified_at);
        });
        return data;
      })
      .catch((err) => {
        throw err;
      });
  };

  const handleGetCoverageData = (data) => {
    const ids = [];
    data.forEach((item) => {
      const isOutputAdded = ids.findIndex(
        (output) => output?.docName === item?.doc_name
      );

      if (isOutputAdded > -1) {
        return;
      }

      if (
        item?.output !== undefined &&
        [...listOfDocs].includes(item?.doc_name)
      ) {
        ids.push({
          promptOutputId: item?.prompt_output_id,
          docName: item?.doc_name,
        });
      }
    });
    setOutputIds(ids);
    setCoverage(ids?.length);
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
                  disabled={disableLlmOrDocChange.includes(
                    promptDetails?.prompt_id
                  )}
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
                  disabled={disableLlmOrDocChange.includes(
                    promptDetails?.prompt_id
                  )}
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
                <Col span={16}>
                  <EditableText
                    isEditing={isEditingTitle}
                    setIsEditing={setIsEditingTitle}
                    text={promptKey}
                    setText={setPromptKey}
                    promptId={promptDetails?.prompt_id}
                    defaultText={promptDetails?.prompt_key}
                    handleChange={handleChange}
                  />
                </Col>
                <Col span={8} className="display-flex-right">
                  {isCoverageLoading && (
                    <Tag
                      icon={<LoadingOutlined spin />}
                      color="processing"
                      className="display-flex-align-center"
                    >
                      Generating Response
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
                    </>
                  )}
                  <Tooltip title="Edit">
                    <Button
                      size="small"
                      type="text"
                      className="display-flex-align-center"
                      onClick={enableEdit}
                      disabled={disableLlmOrDocChange.includes(
                        promptDetails?.prompt_id
                      )}
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
                  <Tooltip title="Run">
                    <Button
                      size="small"
                      type="text"
                      onClick={handleRun}
                      disabled={
                        (updateStatus?.promptId === promptDetails?.prompt_id &&
                          updateStatus?.status ===
                            promptStudioUpdateStatus.isUpdating) ||
                        disableLlmOrDocChange.includes(promptDetails?.prompt_id)
                      }
                    >
                      <PlayCircleOutlined className="prompt-card-actions-head" />
                    </Button>
                  </Tooltip>
                  <ConfirmModal
                    handleConfirm={() => handleDelete(promptDetails?.prompt_id)}
                    content="The prompt will be permanently deleted."
                  >
                    <Tooltip title="Delete">
                      <Button
                        size="small"
                        type="text"
                        disabled={disableLlmOrDocChange.includes(
                          promptDetails?.prompt_id
                        )}
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
              />
            </Space>
          </div>
        </>
        <>
          <Divider className="prompt-card-divider" />
          <Space
            direction="vertical"
            className={`prompt-card-comp-layout ${
              !(
                isRunLoading ||
                (result?.output !== undefined && outputIds?.length > 0)
              ) && "prompt-card-comp-layout-border"
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
                  icon={<SearchOutlined className="font-size-12" />}
                  loading={isCoverageLoading}
                  onClick={() => setOpenOutputForDoc(true)}
                  disabled={outputIds?.length === 0}
                >
                  <Typography.Link className="font-size-12">
                    Coverage: {coverage} of {listOfDocs?.length || 0} docs
                  </Typography.Link>
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
                  disabled={disableLlmOrDocChange.includes(
                    promptDetails?.prompt_id
                  )}
                  onChange={(value) => handleTypeChange(value)}
                />
              </div>
            </div>
            <div className="prompt-card-llm-profiles">
              {llmProfiles?.length > 0 &&
              promptDetails?.profile_manager?.length > 0 ? (
                <div>
                  <Tag>{llmProfiles[page - 1]?.llm}</Tag>
                  <Tag>{llmProfiles[page - 1]?.vector_store}</Tag>
                  <Tag>{llmProfiles[page - 1]?.embedding_model}</Tag>
                  <Tag>{llmProfiles[page - 1]?.x2text}</Tag>
                  <Tag>{`${llmProfiles[page - 1]?.chunk_size}/${
                    llmProfiles[page - 1]?.chunk_overlap
                  }/${llmProfiles[page - 1]?.retrieval_strategy}/${
                    llmProfiles[page - 1]?.similarity_top_k
                  }/${llmProfiles[page - 1]?.section}`}</Tag>
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
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id)
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
                    disableLlmOrDocChange.includes(promptDetails?.prompt_id)
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
        {(isRunLoading ||
          (result?.output !== undefined && outputIds?.length > 0)) && (
          <>
            <Divider className="prompt-card-divider" />
            <div className="prompt-card-result prompt-card-div">
              {isRunLoading ? (
                <Spin indicator={<SpinnerLoader size="small" />} />
              ) : (
                <Typography.Paragraph className="prompt-card-res font-size-12">
                  <div>{displayPromptResult(result?.output)}</div>
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
      />
    </>
  );
}

PromptCard.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChange: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updateStatus: PropTypes.object.isRequired,
};

export { PromptCard };
