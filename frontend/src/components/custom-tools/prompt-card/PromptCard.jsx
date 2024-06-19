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
    setSelectedLlmProfileId(
      promptDetails?.profile_manager || llmProfiles[0].profile_id
    );
  }, [promptDetails]);

  useEffect(() => {
    resetInfoMsgs();
    handleGetOutput();
    handleGetCoverage();
    if (isSinglePassExtractLoading) {
      return;
    }
    if (selectedLlmProfileId !== promptDetails?.profile_id) {
      handleChange(
        selectedLlmProfileId,
        promptDetails?.prompt_id,
        "profile_manager"
      );
    }
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
  const handleRun = (
    profileManagerId,
    coverAllDoc = true,
    selectedLlmProfiles = []
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
        !(!coverAllDoc && selectedLlmProfiles.length > 0)
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

    handleIsRunLoading(
      selectedDoc.document_id,
      profileManagerId || selectedLlmProfileId,
      true
    );
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
      handleIsRunLoading(selectedDoc.document_id, selectedLlmProfileId, false);
      setCoverageTotal(1);
      handleCoverage(selectedLlmProfileId);
      setAlertDetails({
        type: "error",
        content: `Summary needs to be indexed before running the prompt - ${selectedDoc?.document_name}.`,
      });
      return;
    }

    handleDocOutputs(docId, true, null);
    if (!profileManagerId) {
      let selectedProfiles = llmProfiles;
      if (!coverAllDoc && selectedLlmProfiles.length > 0) {
        selectedProfiles = llmProfiles.filter((profile) =>
          selectedLlmProfiles.includes(profile.profile_id)
        );
      }
      for (const profile of selectedProfiles) {
        handleIsRunLoading(selectedDoc.document_id, profile.profile_id, true);
        handleRunApiRequest(docId, profile.profile_id)
          .then((res) => {
            const data = res?.data?.output;
            const value = data[promptDetails?.prompt_key];
            if (value || value === 0) {
              setCoverage((prev) => prev + 1);
            }
            handleDocOutputs(docId, false, value);
            handleGetOutput(profile.profile_id);
          })
          .catch((err) => {
            handleIsRunLoading(
              selectedDoc.document_id,
              profile.profile_id,
              false
            );
            handleDocOutputs(docId, false, null);
            setAlertDetails(
              handleException(err, `Failed to generate output for ${docId}`)
            );
          });
        if (coverAllDoc) {
          handleCoverage(profile.profile_id);
        }
      }
    } else {
      handleRunApiRequest(docId, profileManagerId)
        .then((res) => {
          const data = res?.data?.output;
          const value = data[promptDetails?.prompt_key];
          if (value || value === 0) {
            setCoverage((prev) => prev + 1);
          }
          handleDocOutputs(docId, false, value);
          handleGetOutput();
          setCoverageTotal(1);
        })
        .catch((err) => {
          handleIsRunLoading(
            selectedDoc.document_id,
            selectedLlmProfileId,
            false
          );
          handleDocOutputs(docId, false, null);
          setAlertDetails(
            handleException(err, `Failed to generate output for ${docId}`)
          );
        })
        .finally(() => {
          handleIsRunLoading(selectedDoc.document_id, profileManagerId, false);
          setIsCoverageLoading(false);
        });
      if (coverAllDoc) {
        handleCoverage(profileManagerId);
      }
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
      handleDocOutputs(docId, true, null);
      handleRunApiRequest(docId, profileManagerId)
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
          if (listOfDocsToProcess?.length >= totalCoverageValue) {
            setIsCoverageLoading(false);
            return;
          }
          setCoverageTotal(totalCoverageValue);
        });
    });
  };

  const handleRunApiRequest = async (docId, profileManagerId = null) => {
    const promptId = promptDetails?.prompt_id;
    const runId = generateUUID();

    // Update the token usage state with default token usage for a specific document ID
    const tokenUsageId = promptId + "__" + docId + "__" + profileManagerId;
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

    if (profileManagerId) {
      body.profile_manager = profileManagerId;
    }

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

  const handleGetOutput = (profileManager = undefined) => {
    if (!selectedDoc) {
      setResult([]);
      return;
    }

    if (singlePassExtractMode) {
      setResult([]);
      return;
    }

    handleIsRunLoading(
      selectedDoc.document_id,
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
            output: outputResult?.output,
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
          selectedDoc.document_id,
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
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptDetails?.prompt_id}&is_single_pass_extract=${singlePassExtractMode}`;

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
          const tokenUsageId = `single_pass__${selectedDoc?.document_id}`;
          const usage = data.find((item) => item?.run_id !== undefined);

          if (!tokenUsage[tokenUsageId] && usage) {
            setTokenUsage(tokenUsageId, usage?.token_usage);
          }
        } else {
          data.forEach((item) => {
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
    const counts = {};

    // Iterate through each object in the array
    data.forEach((item) => {
      // Create a unique key for each combination of prompt_id and profile_manager
      const key = `${item.prompt_id}_${item.profile_manager}`;

      // If the key exists in the counts object, increment the count
      if (counts[key]) {
        counts[key].count += 1;
      } else {
        // Otherwise, add the key to the counts object with an initial count of 1
        counts[key] = {
          prompt_id: item.prompt_id,
          profile_manager: item.profile_manager,
          count: 1,
        };
      }
    });
    setCoverage(counts);
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
