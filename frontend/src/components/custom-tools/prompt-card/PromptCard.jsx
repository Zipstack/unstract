import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import {
  generateUUID,
  pollForCompletion,
  promptStudioUpdateStatus,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { OutputForDocModal } from "../output-for-doc-modal/OutputForDocModal";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { PromptCardItems } from "./PromptCardItems";
import "./PromptCard.css";
import usePromptOutput from "../../../hooks/usePromptOutput";
import { handleUpdateStatus } from "./constants";

let promptRunApiSps;
try {
  promptRunApiSps =
    require("../../../plugins/simple-prompt-studio/helper").promptRunApiSps;
} catch {
  // The component will remain null of it is not available
}

function PromptCard({
  promptDetails,
  handleChangePromptCard,
  handleDelete,
  updatePlaceHolder,
  promptOutputs,
  enforceTypeList,
  setUpdatedPromptsCopy,
}) {
  const [promptDetailsState, setPromptDetailsState] = useState({});
  const [isPromptDetailsStateUpdated, setIsPromptDetailsStateUpdated] =
    useState(false);
  const [updateStatus, setUpdateStatus] = useState({
    promptId: null,
    status: null,
  });
  const [isRunLoading, setIsRunLoading] = useState({});
  const [promptKey, setPromptKey] = useState("");
  const [promptText, setPromptText] = useState("");
  const [selectedLlmProfileId, setSelectedLlmProfileId] = useState(null);
  const [coverage, setCoverage] = useState({});
  const [coverageTotal, setCoverageTotal] = useState(0);
  const [isCoverageLoading, setIsCoverageLoading] = useState(false);
  const [openOutputForDoc, setOpenOutputForDoc] = useState(false);
  const [progressMsg, setProgressMsg] = useState({});
  const [docOutputs, setDocOutputs] = useState([]);
  const [timers, setTimers] = useState({}); // Prompt run timer
  const [spsLoading, setSpsLoading] = useState({});
  const {
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
  } = useCustomToolStore();
  const { messages } = useSocketCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { updatePromptOutputState } = usePromptOutput();

  useEffect(() => {
    if (
      isPromptDetailsStateUpdated ||
      !Object.keys(promptDetails || {})?.length
    )
      return;
    setPromptDetailsState(promptDetails);
    setIsPromptDetailsStateUpdated(true);
  }, [promptDetails]);

  useEffect(() => {
    // Find the latest message that matches the criteria
    const msg = [...messages]
      .reverse()
      .find(
        (item) =>
          (item?.component?.prompt_id === promptDetailsState?.prompt_id ||
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
      promptDetailsState?.profile_manager || llmProfiles[0]?.profile_id
    );
  }, [promptDetailsState]);

  useEffect(() => {
    resetInfoMsgs();
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
    const promptId = promptDetailsState?.prompt_id;
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
  }, [docOutputs]);

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

  const handleChange = async (
    event,
    promptId,
    dropdownItem,
    isUpdateStatus = false
  ) => {
    let name = "";
    let value = "";
    if (dropdownItem?.length) {
      name = dropdownItem;
      value = event;
    } else {
      name = event.target.name;
      value = event.target.value;
    }

    const prevPromptDetailsState = { ...promptDetailsState };

    const updatedPromptDetailsState = { ...promptDetailsState };
    updatedPromptDetailsState[name] = value;

    handleUpdateStatus(
      isUpdateStatus,
      promptId,
      promptStudioUpdateStatus.isUpdating,
      setUpdateStatus
    );
    setPromptDetailsState(updatedPromptDetailsState);
    return handleChangePromptCard(name, value, promptId)
      .then((res) => {
        const data = res?.data;
        setUpdatedPromptsCopy((prev) => {
          prev[promptId] = data;
          return prev;
        });
        handleUpdateStatus(
          isUpdateStatus,
          promptId,
          promptStudioUpdateStatus.done,
          setUpdateStatus
        );
      })
      .catch(() => {
        handleUpdateStatus(isUpdateStatus, promptId, null, setUpdateStatus);
        setPromptDetailsState(prevPromptDetailsState);
      })
      .finally(() => {
        if (isUpdateStatus) {
          setTimeout(() => {
            handleUpdateStatus(true, promptId, null, setUpdateStatus);
          }, 3000);
        }
      });
  };

  // Function to update loading state for a specific document and profile
  const handleIsRunLoading = (docId, profileId, isLoading) => {
    setIsRunLoading((prevLoadingProfiles) => ({
      ...prevLoadingProfiles,
      [`${docId}_${profileId}`]: isLoading,
    }));
  };

  const handleSelectDefaultLLM = (llmProfileId) => {
    setSelectedLlmProfileId(llmProfileId);
    handleChange(
      llmProfileId,
      promptDetailsState?.prompt_id,
      "profile_manager"
    );
  };

  const handleTypeChange = (value) => {
    handleChange(value, promptDetailsState?.prompt_id, "enforce_type", true);
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
        !promptDetailsState?.profile_manager?.length &&
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
          promptDetailsState?.prompt_id,
          profile?.profile_id,
          true,
          null
        );
        setIsCoverageLoading(true);

        handleIsRunLoading(selectedDoc?.document_id, profile?.profile_id, true);

        const startTime = Date.now();
        handleRunApiRequest(docId, profile?.profile_id)
          .then((res) => {
            const data = res?.data || [];
            const value = data[0]?.output;

            updatePromptOutputState(data, false);
            handleDocOutputs(
              docId,
              promptDetailsState?.prompt_id,
              profile?.profile_id,
              false,
              value
            );

            updateDocCoverage(
              promptDetailsState?.prompt_id,
              profile?.profile_id,
              docId
            );
          })
          .catch((err) => {
            handleDocOutputs(
              docId,
              promptDetailsState?.prompt_id,
              profile?.profile_id,
              false,
              null
            );
            setAlertDetails(
              handleException(err, `Failed to generate output for ${docId}`)
            );
          })
          .finally(() => {
            handleIsRunLoading(docId, profile?.profile_id, false);
            setIsCoverageLoading(false);
            const endTime = Date.now();
            updateTimers(startTime, endTime, profile?.profile_id);
          });
        runCoverageForAllDoc(coverAllDoc, profile.profile_id);
      }
    } else {
      handleIsRunLoading(selectedDoc?.document_id, profileManagerId, true);
      handleDocOutputs(
        docId,
        promptDetailsState?.prompt_id,
        profileManagerId,
        true,
        null
      );
      const startTime = Date.now();
      handleRunApiRequest(docId, profileManagerId)
        .then((res) => {
          const data = res?.data || [];
          const value = data[0]?.output;

          updatePromptOutputState(data, false);
          updateDocCoverage(
            promptDetailsState?.prompt_id,
            profileManagerId,
            docId
          );
          handleDocOutputs(
            docId,
            promptDetailsState?.prompt_id,
            profileManagerId,
            false,
            value
          );
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
            promptDetailsState?.prompt_id,
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
          const endTime = Date.now();
          updateTimers(startTime, endTime, profileManagerId);
        });
      runCoverageForAllDoc(coverAllDoc, profileManagerId);
    }
  };

  const updateTimers = (startTime, endTime, profileManagerId) => {
    setTimers((prev) => {
      prev[profileManagerId] = {
        startTime,
        endTime,
      };
      return prev;
    });
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
        promptDetailsState?.prompt_id,
        profileManagerId,
        true,
        null
      );
      handleRunApiRequest(docId, profileManagerId)
        .then((res) => {
          const data = res?.data || [];
          const outputValue = data[0]?.output;
          updateDocCoverage(
            promptDetailsState?.prompt_id,
            profileManagerId,
            docId
          );
          handleDocOutputs(
            docId,
            promptDetailsState?.prompt_id,
            profileManagerId,
            false,
            outputValue
          );
        })
        .catch((err) => {
          handleDocOutputs(
            docId,
            promptDetailsState?.prompt_id,
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
    const promptId = promptDetailsState?.prompt_id;
    const runId = generateUUID();
    const maxWaitTime = 30 * 1000; // 30 seconds
    const pollingInterval = 5000; // 5 seconds

    const body = {
      document_id: docId,
      id: promptId,
    };

    if (profileManagerId) {
      body.profile_manager = profileManagerId;
      let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/fetch_response/${details?.tool_id}`;
      if (!isSimplePromptStudio) {
        body["run_id"] = runId;
      } else {
        body["sps_id"] = details?.tool_id;
        url = promptRunApiSps;
      }

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
        });
    }
  };

  return (
    <>
      <PromptCardItems
        promptDetails={promptDetailsState}
        enforceTypeList={enforceTypeList}
        isRunLoading={isRunLoading}
        promptKey={promptKey}
        setPromptKey={setPromptKey}
        promptText={promptText}
        setPromptText={setPromptText}
        coverage={coverage}
        progressMsg={progressMsg}
        handleRun={handleRun}
        handleChange={handleChange}
        handleTypeChange={handleTypeChange}
        handleDelete={handleDelete}
        updateStatus={updateStatus}
        updatePlaceHolder={updatePlaceHolder}
        isCoverageLoading={isCoverageLoading}
        setOpenOutputForDoc={setOpenOutputForDoc}
        selectedLlmProfileId={selectedLlmProfileId}
        handleSelectDefaultLLM={handleSelectDefaultLLM}
        timers={timers}
        spsLoading={spsLoading}
        handleSpsLoading={handleSpsLoading}
        promptOutputs={promptOutputs}
      />
      <OutputForDocModal
        open={openOutputForDoc}
        setOpen={setOpenOutputForDoc}
        promptId={promptDetailsState?.prompt_id}
        promptKey={promptDetailsState?.prompt_key}
        profileManagerId={selectedLlmProfileId}
        docOutputs={docOutputs}
      />
    </>
  );
}

PromptCard.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updatePlaceHolder: PropTypes.string,
  promptOutputs: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array.isRequired,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
};

export { PromptCard };
