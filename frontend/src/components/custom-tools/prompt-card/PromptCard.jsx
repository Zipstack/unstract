import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  defaultTokenUsage,
  generateUUID,
  pollForCompletion,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { OutputForDocModal } from "../output-for-doc-modal/OutputForDocModal";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import useTokenUsage from "../../../hooks/useTokenUsage";
import { useTokenUsageStore } from "../../../store/token-usage-store";
import { PromptCardItems } from "./PromptCardItems";
import "./PromptCard.css";

const EvalModal = null;
const getEvalMetrics = (param1, param2) => {
  return [];
};

let promptRunApiSps;
let promptOutputApiSps;
try {
  promptRunApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptRunApiSps;
  promptOutputApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptOutputApiSps;
} catch {
  // The component will remain null of it is not available
}
let publicOutputsApi;
try {
  publicOutputsApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicOutputsApi;
} catch {
  // The component will remain null of it is not available
}
function PromptCard({
  promptDetails,
  handleChange,
  handleDelete,
  updateStatus,
  updatePlaceHolder,
}) {
  const [enforceTypeList, setEnforceTypeList] = useState([]);
  const [isRunLoading, setIsRunLoading] = useState({});
  const [promptKey, setPromptKey] = useState("");
  const [promptText, setPromptText] = useState("");
  const [selectedLlmProfileId, setSelectedLlmProfileId] = useState(null);
  const [openEval, setOpenEval] = useState(false);
  const [result, setResult] = useState([]);
  const [coverage, setCoverage] = useState({});
  const [coverageTotal, setCoverageTotal] = useState(0);
  const [isCoverageLoading, setIsCoverageLoading] = useState(false);
  const [openOutputForDoc, setOpenOutputForDoc] = useState(false);
  const [progressMsg, setProgressMsg] = useState({});
  const [docOutputs, setDocOutputs] = useState([]);
  const [timers, setTimers] = useState({});
  const [spsLoading, setSpsLoading] = useState({});
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
    isSimplePromptStudio,
    isPublicSource,
  } = useCustomToolStore();
  const { logs } = useSocketLogsStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { tokenUsage, setTokenUsage } = useTokenUsageStore();
  const { getTokenUsage } = useTokenUsage();
  const { id } = useParams();

  useEffect(() => {
    const outputTypeData = getDropdownItems("output_type") || {};
    const dropdownList1 = Object.keys(outputTypeData).map((item) => {
      return { value: outputTypeData[item] };
    });
    setEnforceTypeList(dropdownList1);
  }, []);

  useEffect(() => {
    // Find the latest message that matches the criteria
    const msg = [...logs]
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
  }, [logs]);

  useEffect(() => {
    setSelectedLlmProfileId(
      promptDetails?.profile_manager || llmProfiles[0]?.profile_id
    );
  }, [promptDetails]);

  useEffect(() => {
    resetInfoMsgs();
    handleGetOutput();
    handleGetCoverage();
  }, [
    selectedLlmProfileId,
    selectedDoc,
    listOfDocs,
    singlePassExtractMode,
    isSinglePassExtractLoading,
    defaultLlmProfile,
  ]);

  useEffect(() => {
    let listOfIds = [...disableLlmOrDocChange];
    const promptId = promptDetails?.prompt_id;
    const isIncluded = listOfIds.includes(promptId);

    const isDocLoading = docOutputs?.some(
      (doc) => doc?.key?.startsWith(`${promptId}__`) && doc?.isLoading
    );

    if ((isIncluded && isDocLoading) || (!isIncluded && !isDocLoading)) {
      return;
    }

    if (isIncluded && !isDocLoading) {
      listOfIds = listOfIds.filter((item) => item !== promptId);
    }

    if (!isIncluded && isDocLoading) {
      listOfIds.push(promptId);
    }

    updateCustomTool({ disableLlmOrDocChange: listOfIds });
  }, [docOutputs, promptDetails, updateCustomTool]);

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
    const isProfilePresent = llmProfiles?.some(
      (profile) => profile?.profile_id === defaultLlmProfile
    );

    // If selectedLlmProfileId is not present, set it to null
    if (!isProfilePresent) {
      setSelectedLlmProfileId(null);
    }
  }, [llmProfiles]);

  // Function to update loading state for a specific document and profile
  const handleIsRunLoading = (docId, profileId, isLoading) => {
    setIsRunLoading((prevLoadingProfiles) => ({
      ...prevLoadingProfiles,
      [`${docId}_${profileId}`]: isLoading,
    }));
  };

  const handleSelectDefaultLLM = (llmProfileId) => {
    setSelectedLlmProfileId(llmProfileId);
    handleChange(llmProfileId, promptDetails?.prompt_id, "profile_manager");
  };

  const handleTypeChange = (value) => {
    handleChange(value, promptDetails?.prompt_id, "enforce_type", true);
  };

  const handleDocOutputs = (docId, promptId, profileId, isLoading, output) => {
    if (isSimplePromptStudio) {
      return;
    }
    setDocOutputs((prev) => {
      const updatedDocOutputs = [...prev];
      const key = `${promptId}__${docId}__${profileId}`;
      // Update the entry for the provided docId with isLoading and output
      const newData = {
        key,
        isLoading,
        output,
      };
      const index = updatedDocOutputs.findIndex((item) => item.key === key);

      if (index !== -1) {
        // Update the existing object
        updatedDocOutputs[index] = newData;
      } else {
        // Append the new object
        updatedDocOutputs.push(newData);
      }
      return updatedDocOutputs;
    });
  };

  const handleSpsLoading = (docId, isLoadingStatus) => {
    setSpsLoading((prev) => ({
      ...prev,
      [docId]: isLoadingStatus,
    }));
  };

  // Generate the result for the currently selected document
  const handleRun = (
    profileManagerId,
    coverAllDoc = true,
    selectedLlmProfiles = [],
    runAllLLM = false
  ) => {
    try {
      setPostHogCustomEvent("ps_prompt_run", {
        info: "Click on 'Run Prompt' button (Multi Pass)",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    const validateInputs = (
      profileManagerId,
      selectedLlmProfiles,
      coverAllDoc
    ) => {
      if (
        !profileManagerId &&
        !promptDetails?.profile_manager?.length &&
        !(!coverAllDoc && selectedLlmProfiles?.length > 0) &&
        !isSimplePromptStudio
      ) {
        setAlertDetails({
          type: "error",
          content: "LLM Profile is not selected",
        });
        return true;
      }

      if (!selectedDoc) {
        setAlertDetails({
          type: "error",
          content: "Document not selected",
        });
        return true;
      }

      if (!promptKey) {
        setAlertDetails({
          type: "error",
          content: "Prompt key cannot be empty",
        });
        return true;
      }

      if (!promptText) {
        setAlertDetails({
          type: "error",
          content: "Prompt cannot be empty",
        });
        return true;
      }

      return false;
    };

    if (validateInputs(profileManagerId, selectedLlmProfiles, coverAllDoc)) {
      return;
    }
    setIsCoverageLoading(true);
    setCoverageTotal(0);
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
      handleIsRunLoading(selectedDoc?.document_id, selectedLlmProfileId, false);
      setCoverageTotal(1);
      handleCoverage(selectedLlmProfileId);
      setAlertDetails({
        type: "error",
        content: `Summary needs to be indexed before running the prompt - ${selectedDoc?.document_name}.`,
      });
      return;
    }

    if (runAllLLM) {
      let selectedProfiles = llmProfiles;
      if (selectedLlmProfiles?.length) {
        selectedProfiles = llmProfiles.filter((profile) =>
          selectedLlmProfiles.includes(profile?.profile_id)
        );
      }
      for (const profile of selectedProfiles) {
        handleDocOutputs(
          docId,
          promptDetails?.prompt_id,
          profile?.profile_id,
          true,
          null
        );
        setIsCoverageLoading(true);

        handleIsRunLoading(selectedDoc?.document_id, profile?.profile_id, true);
        handleRunApiRequest(docId, profile?.profile_id)
          .then((res) => {
            const data = res?.data?.output;
            const value = data[promptDetails?.prompt_key];
            handleDocOutputs(
              docId,
              promptDetails?.prompt_id,
              profile?.profile_id,
              false,
              value
            );
            handleGetOutput(profile?.profile_id);
            updateDocCoverage(
              promptDetails?.prompt_id,
              profile?.profile_id,
              docId
            );
          })
          .catch((err) => {
            handleIsRunLoading(docId, profile?.profile_id, false);
            handleDocOutputs(
              docId,
              promptDetails?.prompt_id,
              profile?.profile_id,
              false,
              null
            );
            setAlertDetails(
              handleException(err, `Failed to generate output for ${docId}`)
            );
          })
          .finally(() => {
            setIsCoverageLoading(false);
          });
        runCoverageForAllDoc(coverAllDoc, profile.profile_id);
      }
    } else {
      handleIsRunLoading(selectedDoc?.document_id, profileManagerId, true);
      handleDocOutputs(
        docId,
        promptDetails?.prompt_id,
        profileManagerId,
        true,
        null
      );
      handleRunApiRequest(docId, profileManagerId)
        .then((res) => {
          const data = res?.data?.output;
          const value = data[promptDetails?.prompt_key];
          updateDocCoverage(promptDetails?.prompt_id, profileManagerId, docId);
          handleDocOutputs(
            docId,
            promptDetails?.prompt_id,
            profileManagerId,
            false,
            value
          );
          handleGetOutput();
          setCoverageTotal(1);
        })
        .catch((err) => {
          handleIsRunLoading(
            selectedDoc?.document_id,
            selectedLlmProfileId,
            false
          );
          handleDocOutputs(
            docId,
            promptDetails?.prompt_id,
            profileManagerId,
            false,
            null
          );
          setAlertDetails(
            handleException(err, `Failed to generate output for ${docId}`)
          );
        })
        .finally(() => {
          setIsCoverageLoading(false);
          handleIsRunLoading(selectedDoc?.document_id, profileManagerId, false);
        });
      runCoverageForAllDoc(coverAllDoc, profileManagerId);
    }
  };

  const runCoverageForAllDoc = (coverAllDoc, profileManagerId) => {
    if (coverAllDoc) {
      handleCoverage(profileManagerId);
    }
  };

  // Get the coverage for all the documents except the one that's currently selected
  const handleCoverage = (profileManagerId) => {
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

      setIsCoverageLoading(true);
      handleDocOutputs(
        docId,
        promptDetails?.prompt_id,
        profileManagerId,
        true,
        null
      );
      handleRunApiRequest(docId, profileManagerId)
        .then((res) => {
          const data = res?.data?.output;
          const outputValue = data[promptDetails?.prompt_key];
          updateDocCoverage(promptDetails?.prompt_id, profileManagerId, docId);
          handleDocOutputs(
            docId,
            promptDetails?.prompt_id,
            profileManagerId,
            false,
            outputValue
          );
        })
        .catch((err) => {
          handleDocOutputs(
            docId,
            promptDetails?.prompt_id,
            profileManagerId,
            false,
            null
          );
          setAlertDetails(
            handleException(err, `Failed to generate output for ${docId}`)
          );
        })
        .finally(() => {
          totalCoverageValue++;
          if (listOfDocsToProcess?.length >= totalCoverageValue) {
            setIsCoverageLoading(false);
            return;
          }
          setCoverageTotal(totalCoverageValue);
        });
    });
  };

  const updateDocCoverage = (promptId, profileManagerId, docId) => {
    setCoverage((prevCoverage) => {
      const keySuffix = `${promptId}_${profileManagerId}`;
      const key = singlePassExtractMode ? `singlepass_${keySuffix}` : keySuffix;

      // Create a shallow copy of the previous coverage state
      const updatedCoverage = { ...prevCoverage };

      // If the key exists in the updated coverage object, update the docs_covered array
      if (updatedCoverage[key]) {
        if (!updatedCoverage[key].docs_covered.includes(docId)) {
          updatedCoverage[key].docs_covered = [
            ...updatedCoverage[key].docs_covered,
            docId,
          ];
        }
      } else {
        // Otherwise, add the key to the updated coverage object with the new entry
        updatedCoverage[key] = {
          prompt_id: promptId,
          profile_manager: profileManagerId,
          docs_covered: [docId],
        };
      }

      return updatedCoverage;
    });
  };

  const handleRunApiRequest = async (docId, profileManagerId) => {
    const promptId = promptDetails?.prompt_id;
    const runId = generateUUID();
    const maxWaitTime = 30 * 1000; // 30 seconds
    const pollingInterval = 5000; // 5 seconds
    const tokenUsagepollingInterval = 5000;

    const body = {
      document_id: docId,
      id: promptId,
    };

    if (profileManagerId) {
      body.profile_manager = profileManagerId;
      let intervalId;
      let tokenUsageId;
      let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/fetch_response/${details?.tool_id}`;
      if (!isSimplePromptStudio) {
        body["run_id"] = runId;
        // Update the token usage state with default token usage for a specific document ID
        tokenUsageId = promptId + "__" + docId + "__" + profileManagerId;
        setTokenUsage(tokenUsageId, defaultTokenUsage);

        // Set up an interval to fetch token usage data at regular intervals
        if (
          profileManagerId === selectedLlmProfileId &&
          docId === selectedDoc?.document_id
        ) {
          intervalId = setInterval(
            () => getTokenUsage(runId, tokenUsageId),
            tokenUsagepollingInterval // Fetch token usage data every 5000 milliseconds (5 seconds)
          );
        }
        setTimers((prev) => ({
          ...prev,
          [tokenUsageId]: 0,
        }));
      } else {
        body["sps_id"] = details?.tool_id;
        url = promptRunApiSps;
      }
      const timerIntervalId = startTimer(tokenUsageId);

      const requestOptions = {
        method: "POST",
        url,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: body,
      };

      const makeApiRequest = (requestOptions) => {
        return axiosPrivate(requestOptions);
      };
      const startTime = Date.now();
      return pollForCompletion(
        startTime,
        requestOptions,
        maxWaitTime,
        pollingInterval,
        makeApiRequest
      )
        .then((response) => {
          return response;
        })
        .catch((err) => {
          throw err;
        })
        .finally(() => {
          if (!isSimplePromptStudio) {
            clearInterval(intervalId);
            getTokenUsage(runId, tokenUsageId);
            stopTimer(tokenUsageId, timerIntervalId);
          }
        });
    }
  };

  const handleGetOutput = (profileManager = undefined) => {
    if (!selectedDoc) {
      setResult([]);
      return;
    }

    if (
      !singlePassExtractMode &&
      !isSimplePromptStudio &&
      !selectedLlmProfileId
    ) {
      setResult([]);
      return;
    }

    handleIsRunLoading(
      selectedDoc?.document_id,
      profileManager || selectedLlmProfileId,
      true
    );

    handleOutputApiRequest(true)
      .then((res) => {
        const data = res?.data;
        if (!data || data?.length === 0) {
          setResult([]);
          return;
        }

        const outputResults = data.map((outputResult) => {
          return {
            runId: outputResult?.run_id,
            promptOutputId: outputResult?.prompt_output_id,
            profileManager: outputResult?.profile_manager,
            context: outputResult?.context,
            output: outputResult?.output,
            totalCost: outputResult?.token_usage?.cost_in_dollars,
            evalMetrics: getEvalMetrics(
              promptDetails?.evaluate,
              outputResult?.eval_metrics || []
            ),
          };
        });
        setResult(outputResults);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate the result"));
      })
      .finally(() => {
        handleIsRunLoading(
          selectedDoc?.document_id,
          profileManager || selectedLlmProfileId,
          false
        );
      });
  };

  const handleGetCoverage = () => {
    if (
      (singlePassExtractMode && !defaultLlmProfile) ||
      (!singlePassExtractMode && !selectedLlmProfileId)
    ) {
      setCoverage({});
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
    let url;
    let profileManager = selectedLlmProfileId;
    if (isSimplePromptStudio) {
      url = promptOutputApiSps(
        details?.tool_id,
        promptDetails?.prompt_id,
        null
      );
    } else {
      if (singlePassExtractMode) {
        profileManager = defaultLlmProfile;
      }
      url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptDetails?.prompt_id}&is_single_pass_extract=${singlePassExtractMode}`;
    }
    if (isPublicSource) {
      url = publicOutputsApi(
        id,
        promptDetails?.prompt_id,
        singlePassExtractMode
      );
    }
    if (isOutput) {
      url += `&document_manager=${selectedDoc?.document_id}`;
    }
    if (singlePassExtractMode) {
      url += `&profile_manager=${profileManager}`;
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
          const tokenUsageId = `single_pass__${defaultLlmProfile}__${selectedDoc?.document_id}`;
          const usage = data?.find(
            (item) =>
              item?.profile_manager === defaultLlmProfile &&
              item?.document_manager === selectedDoc?.document_id
          );

          if (usage) {
            setTokenUsage(tokenUsageId, usage?.token_usage);
          }
        } else {
          data?.forEach((item) => {
            const tokenUsageId = `${item?.prompt_id}__${item?.document_manager}__${item?.profile_manager}`;

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
    data?.forEach((item) => {
      updateDocCoverage(
        item?.prompt_id,
        item?.profile_manager,
        item?.document_manager
      );
    });
  };

  const startTimer = (profileId) => {
    setTimers((prev) => ({
      ...prev,
      [profileId]: (prev[profileId] || 0) + 1,
    }));
    return setInterval(() => {
      setTimers((prev) => ({
        ...prev,
        [profileId]: (prev[profileId] || 0) + 1,
      }));
    }, 1000);
  };

  const stopTimer = (profileId, intervalId) => {
    clearInterval(intervalId);
    setTimers((prev) => ({
      ...prev,
      [profileId]: prev[profileId] || 0,
    }));
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
        handleTypeChange={handleTypeChange}
        handleDelete={handleDelete}
        updateStatus={updateStatus}
        updatePlaceHolder={updatePlaceHolder}
        isCoverageLoading={isCoverageLoading}
        setOpenEval={setOpenEval}
        setOpenOutputForDoc={setOpenOutputForDoc}
        selectedLlmProfileId={selectedLlmProfileId}
        handleSelectDefaultLLM={handleSelectDefaultLLM}
        timers={timers}
        spsLoading={spsLoading}
        handleSpsLoading={handleSpsLoading}
        handleGetOutput={handleGetOutput}
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
        profileManagerId={selectedLlmProfileId}
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
