import PropTypes from "prop-types";
import { memo, useEffect, useState } from "react";

import {
  PROMPT_RUN_API_STATUSES,
  promptStudioUpdateStatus,
} from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { OutputForDocModal } from "../output-for-doc-modal/OutputForDocModal";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { PromptCardItems } from "./PromptCardItems";
import "./PromptCard.css";
import { handleUpdateStatus } from "./constants";

const PromptCard = memo(
  ({
    promptDetails,
    handleChangePromptCard,
    handleDelete,
    updatePlaceHolder,
    promptOutputs,
    enforceTypeList,
    setUpdatedPromptsCopy,
    handlePromptRunRequest,
    promptRunStatus,
    coverageCountData,
    isChallenge,
  }) => {
    const [promptDetailsState, setPromptDetailsState] = useState({});
    const [isPromptDetailsStateUpdated, setIsPromptDetailsStateUpdated] =
      useState(false);
    const [updateStatus, setUpdateStatus] = useState({
      promptId: null,
      status: null,
    });
    const [promptKey, setPromptKey] = useState("");
    const [promptText, setPromptText] = useState("");
    const [selectedLlmProfileId, setSelectedLlmProfileId] = useState(null);

    const [isCoverageLoading, setIsCoverageLoading] = useState(false);
    const [openOutputForDoc, setOpenOutputForDoc] = useState(false);
    const [progressMsg, setProgressMsg] = useState({});
    const [spsLoading, setSpsLoading] = useState({});
    const {
      llmProfiles,
      selectedDoc,
      details,
      summarizeIndexStatus,
      updateCustomTool,
    } = useCustomToolStore();
    const { messages } = useSocketCustomToolStore();
    const { setAlertDetails } = useAlertStore();
    const { setPostHogCustomEvent } = usePostHogEvents();

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
      const promptRunStatusKeys = Object.keys(promptRunStatus);

      const coverageLoading = promptRunStatusKeys.some(
        (key) => promptRunStatus[key] === PROMPT_RUN_API_STATUSES.RUNNING
      );
      setIsCoverageLoading(coverageLoading);
    }, [promptRunStatus]);

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

    const handleSelectDefaultLLM = (llmProfileId) => {
      setSelectedLlmProfileId(llmProfileId);
      handleChange(
        llmProfileId,
        promptDetailsState?.prompt_id,
        "profile_manager"
      );
    };

    const handleSelectHighlight = (
      highlightData,
      highlightedPrompt,
      highlightedProfile
    ) => {
      if (
        details?.enable_highlight &&
        promptDetailsState?.enforce_type !== "json"
      ) {
        updateCustomTool({
          selectedHighlight: {
            highlight: highlightData,
            highlightedPrompt: highlightedPrompt,
            highlightedProfile: highlightedProfile,
          },
        });
      }
    };

    const handleTypeChange = (value) => {
      handleChange(value, promptDetailsState?.prompt_id, "enforce_type", true);
    };

    const handleSpsLoading = (docId, isLoadingStatus) => {
      setSpsLoading((prev) => ({
        ...prev,
        [docId]: isLoadingStatus,
      }));
    };

    // Generate the result for the currently selected document
    const handleRun = (promptRunType, promptId, profileId, documentId) => {
      try {
        setPostHogCustomEvent("ps_prompt_run", {
          info: "Click on 'Run Prompt' button (Multi Pass)",
        });
      } catch (err) {
        // If an error occurs while setting custom posthog event, ignore it and continue
      }

      const validateInputs = () => {
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

      if (validateInputs()) {
        return;
      }

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
        setAlertDetails({
          type: "error",
          content: `Summary needs to be indexed before running the prompt - ${selectedDoc?.document_name}.`,
        });
        return;
      }

      handlePromptRunRequest(promptRunType, promptId, profileId, documentId);
    };

    return (
      <>
        <PromptCardItems
          promptDetails={promptDetailsState}
          enforceTypeList={enforceTypeList}
          promptKey={promptKey}
          setPromptKey={setPromptKey}
          promptText={promptText}
          setPromptText={setPromptText}
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
          spsLoading={spsLoading}
          handleSpsLoading={handleSpsLoading}
          promptOutputs={promptOutputs}
          promptRunStatus={promptRunStatus}
          coverageCountData={coverageCountData}
          isChallenge={isChallenge}
          handleSelectHighlight={handleSelectHighlight}
        />
        <OutputForDocModal
          open={openOutputForDoc}
          setOpen={setOpenOutputForDoc}
          promptId={promptDetailsState?.prompt_id}
          promptKey={promptDetailsState?.prompt_key}
          profileManagerId={selectedLlmProfileId}
        />
      </>
    );
  }
);

PromptCard.displayName = "PromptCard";

PromptCard.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  updatePlaceHolder: PropTypes.string,
  promptOutputs: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array.isRequired,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
  handlePromptRunRequest: PropTypes.func.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
  coverageCountData: PropTypes.object.isRequired,
  isChallenge: PropTypes.bool.isRequired,
};

export { PromptCard };
