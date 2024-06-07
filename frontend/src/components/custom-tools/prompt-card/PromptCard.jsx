import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import {
  defaultTokenUsage,
  generateUUID,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { OutputForDocModal } from "../output-for-doc-modal/OutputForDocModal";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import useTokenUsage from "../../../hooks/useTokenUsage";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import { PromptCardItems } from "./PromptCardItems";
import "./PromptCard.css";

const EvalModal = null;
const getEvalMetrics = (param1, param2) => {
  return [];
};

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
  const [promptKey, setPromptKey] = useState("");
  const [promptText, setPromptText] = useState("");
  const [selectedLlmProfileId, setSelectedLlmProfileId] = useState(null);
  const [openEval, setOpenEval] = useState(false);
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
  const {
    getDropdownItems,
    llmProfiles,
    selectedDoc,
    listOfDocs,
    updateCustomTool,
    details,
    defaultLlmProfile,
    disableLlmOrDocChange,
    summarizeIndexStatus,
    singlePassExtractMode,
    isSinglePassExtractLoading,
  } = useCustomToolStore();
  const { messages } = useSocketCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { tokenUsage, setTokenUsage } = useTokenUsageStore();
  const { getTokenUsage } = useTokenUsage();

  useEffect(() => {
    const outputTypeData = getDropdownItems("output_type");
    const dropdownList1 = Object.keys(outputTypeData).map((item) => {
      return { value: outputTypeData[item] };
    });
    setEnforceTypeList(dropdownList1);
  }, []);

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
    setSelectedLlmProfileId(promptDetails?.profile_manager || null);
  }, [promptDetails]);

  useEffect(() => {
    resetInfoMsgs();
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
    if (isCoverageLoading && coverageTotal === listOfDocs?.length) {
      setIsCoverageLoading(false);
      setCoverageTotal(0);
    }
  }, [coverageTotal]);

  const resetInfoMsgs = () => {
    setProgressMsg({}); // Reset Progress Message
  };

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
    handleChange(value, promptDetails?.prompt_id, "enforce_type", true);
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
    try {
      setPostHogCustomEvent("ps_prompt_run", {
        info: "Click on 'Run Prompt' button (Multi Pass)",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

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
    setDocOutputs({});
    resetInfoMsgs();

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
      setIsRunLoading(false);
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
        const data = res?.data?.output;
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
          const data = res?.data?.output;
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
    const runId = generateUUID();

    // Update the token usage state with default token usage for a specific document ID
    const tokenUsageId = promptId + "__" + docId;
    setTokenUsage(tokenUsageId, defaultTokenUsage);

    // Set up an interval to fetch token usage data at regular intervals
    const intervalId = setInterval(
      () => getTokenUsage(runId, tokenUsageId),
      5000 // Fetch token usage data every 5000 milliseconds (5 seconds)
    );

    const body = {
      document_id: docId,
      id: promptId,
      run_id: runId,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/fetch_response/${details?.tool_id}`,
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
      })
      .finally(() => {
        clearInterval(intervalId);
        getTokenUsage(runId, tokenUsageId);
      });
  };

  const handleGetOutput = () => {
    if (!selectedDoc || (!singlePassExtractMode && !selectedLlmProfileId)) {
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
    if (
      (singlePassExtractMode && !defaultLlmProfile) ||
      (!singlePassExtractMode && !selectedLlmProfileId)
    ) {
      setCoverage(0);
      return;
    }

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
    let profileManager = selectedLlmProfileId;
    if (singlePassExtractMode) {
      profileManager = defaultLlmProfile;
    }
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptDetails?.prompt_id}&profile_manager=${profileManager}&is_single_pass_extract=${singlePassExtractMode}`;

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
      .then((res) => {
        const data = res?.data || [];

        if (singlePassExtractMode) {
          const tokenUsageId = `single_pass__${selectedDoc?.document_id}`;
          const usage = data.find((item) => item?.run_id !== undefined);

          if (!tokenUsage[tokenUsageId] && usage) {
            setTokenUsage(tokenUsageId, usage?.token_usage);
          }
        } else {
          data.forEach((item) => {
            const tokenUsageId = `${item?.prompt_id}__${item?.document_manager}`;

            if (tokenUsage[tokenUsageId] === undefined) {
              setTokenUsage(tokenUsageId, item?.token_usage);
            }
          });
        }
        return res;
      })
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

  return (
    <>
      <PromptCardItems
        promptDetails={promptDetails}
        enforceTypeList={enforceTypeList}
        isRunLoading={isRunLoading}
        promptKey={promptKey}
        setPromptKey={setPromptKey}
        promptText={promptText}
        setPromptText={setPromptText}
        result={result}
        coverage={coverage}
        progressMsg={progressMsg}
        handleRun={handleRun}
        handleChange={handleChange}
        handlePageLeft={handlePageLeft}
        handlePageRight={handlePageRight}
        handleTypeChange={handleTypeChange}
        handleDelete={handleDelete}
        updateStatus={updateStatus}
        updatePlaceHolder={updatePlaceHolder}
        isCoverageLoading={isCoverageLoading}
        setOpenEval={setOpenEval}
        setOpenOutputForDoc={setOpenOutputForDoc}
        selectedLlmProfileId={selectedLlmProfileId}
        page={page}
      />
      {EvalModal && !singlePassExtractMode && (
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
