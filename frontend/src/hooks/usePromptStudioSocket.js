import { useCallback, useContext, useEffect } from "react";
import { generateApiRunStatusId } from "../helpers/GetStaticData";
import { SocketContext } from "../helpers/SocketContext";
import { useAlertStore } from "../store/alert-store";
import { useCustomToolStore } from "../store/custom-tool-store";
import { usePromptRunStatusStore } from "../store/prompt-run-status-store";
import { useExceptionHandler } from "./useExceptionHandler";
import usePromptOutput from "./usePromptOutput";

const PROMPT_STUDIO_RESULT_EVENT = "prompt_studio_result";

/**
 * Hook that listens for `prompt_studio_result` Socket.IO events emitted by
 * backend Celery tasks (fetch_response, single_pass_extraction, index_document).
 *
 * On completion it feeds the result into the prompt-output store and clears
 * the corresponding run-status entries so the UI stops showing spinners.
 */
const usePromptStudioSocket = () => {
  const socket = useContext(SocketContext);
  const { removePromptStatus, clearPromptStatusById } =
    usePromptRunStatusStore();
  const { updateCustomTool, deleteIndexDoc } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { updatePromptOutputState } = usePromptOutput();

  const clearResultStatuses = useCallback(
    (data) => {
      if (!Array.isArray(data)) {
        return;
      }
      data.forEach((item) => {
        const promptId = item?.prompt_id;
        const docId = item?.document_manager;
        const profileId = item?.profile_manager;
        if (promptId && docId && profileId) {
          const statusKey = generateApiRunStatusId(docId, profileId);
          removePromptStatus(promptId, statusKey);
        }
      });
    },
    [removePromptStatus],
  );

  const handleCompleted = useCallback(
    (operation, result) => {
      if (operation === "fetch_response") {
        const data = Array.isArray(result) ? result : [];
        updatePromptOutputState(data, false);
        clearResultStatuses(data);
        setAlertDetails({
          type: "success",
          content: "Prompt execution completed successfully.",
        });
      } else if (operation === "single_pass_extraction") {
        const data = Array.isArray(result) ? result : [];
        updatePromptOutputState(data, false);
        updateCustomTool({ isSinglePassExtractLoading: false });
        clearResultStatuses(data);
        setAlertDetails({
          type: "success",
          content: "Single pass extraction completed successfully.",
        });
      } else if (operation === "index_document") {
        const docId = result?.document_id;
        if (docId) {
          deleteIndexDoc(docId);
        }
        setAlertDetails({
          type: "success",
          content: result?.message || "Document indexed successfully.",
        });
      }
    },
    [
      updatePromptOutputState,
      clearResultStatuses,
      updateCustomTool,
      setAlertDetails,
      deleteIndexDoc,
    ],
  );

  const handleFailed = useCallback(
    (operation, error, extra) => {
      setAlertDetails({
        type: "error",
        content: error || `${operation} failed`,
      });
      if (operation === "single_pass_extraction") {
        updateCustomTool({ isSinglePassExtractLoading: false });
      } else if (operation === "index_document") {
        const docId = extra?.document_id;
        if (docId) {
          deleteIndexDoc(docId);
        }
      }

      // Clear spinner for prompt operations so buttons re-enable
      if (
        operation === "fetch_response" ||
        operation === "single_pass_extraction"
      ) {
        const promptIds = extra?.prompt_ids || [];
        const docId = extra?.document_id;
        const profileId = extra?.profile_manager_id;
        if (docId && profileId) {
          // Specific clearing (ideal path)
          const statusKey = generateApiRunStatusId(docId, profileId);
          promptIds.forEach((promptId) => {
            removePromptStatus(promptId, statusKey);
          });
        } else {
          // Fallback: clear ALL statuses for these prompts
          promptIds.forEach((promptId) => {
            clearPromptStatusById(promptId);
          });
        }
      }
    },
    [
      setAlertDetails,
      updateCustomTool,
      deleteIndexDoc,
      removePromptStatus,
      clearPromptStatusById,
    ],
  );

  const onResult = useCallback(
    (payload) => {
      try {
        const msg = payload?.data || payload;
        const { status, operation, result, error, ...extra } = msg;

        if (status === "completed") {
          handleCompleted(operation, result);
        } else if (status === "failed") {
          handleFailed(operation, error, extra);
        }
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to process prompt studio result"),
        );
      }
    },
    [handleCompleted, handleFailed, setAlertDetails, handleException],
  );

  useEffect(() => {
    if (!socket) {
      return;
    }

    socket.on(PROMPT_STUDIO_RESULT_EVENT, onResult);
    return () => {
      socket.off(PROMPT_STUDIO_RESULT_EVENT, onResult);
    };
  }, [socket, onResult]);
};

export default usePromptStudioSocket;
