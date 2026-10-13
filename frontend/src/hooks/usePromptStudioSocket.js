import { useCallback, useContext, useEffect } from "react";
import { generateApiRunStatusId } from "../helpers/GetStaticData";
import { SocketContext } from "../helpers/SocketContext";
import { useAlertStore } from "../store/alert-store";
import { useCustomToolStore } from "../store/custom-tool-store";
import { usePromptRunStatusStore } from "../store/prompt-run-status-store";
import { useExceptionHandler } from "./useExceptionHandler";
import usePostHogEvents from "./usePostHogEvents";
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
  const { updateCustomTool, deleteIndexDoc, selectedDoc, details } =
    useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { updatePromptOutputState, promptOutputApi } = usePromptOutput();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const clearPromptStatuses = useCallback(
    (promptIds, docId, profileId) => {
      if (!docId || !profileId) {
        return;
      }
      const statusKey = generateApiRunStatusId(docId, profileId);
      (promptIds || []).forEach((promptId) => {
        removePromptStatus(promptId, statusKey);
      });
    },
    [removePromptStatus],
  );

  const handleCompleted = useCallback(
    async (operation, result, extra) => {
      if (
        operation === "fetch_response" ||
        operation === "single_pass_extraction"
      ) {
        // Use inline result if present (backward compat with old backend),
        // otherwise refetch via API to avoid DATA_UPLOAD_MAX_MEMORY_SIZE.
        let data = Array.isArray(result) ? result : [];
        const hadInlineResult = data.length > 0;
        if (data.length === 0) {
          try {
            const res = await promptOutputApi(
              details?.tool_id,
              extra?.document_id,
              null,
              extra?.profile_manager_id,
              operation === "single_pass_extraction",
            );
            data = Array.isArray(res?.data) ? res.data : [];
          } catch {
            // API fetch failed — proceed with empty data
          }
        }
        console.log(
          "[Socket] handleCompleted:",
          operation,
          "inline:",
          hadInlineResult,
          "items:",
          data.length,
        );
        // Replace the store fully so a refetch with all pages cannot
        // lose entries via the merge/updateCoverage path.
        updatePromptOutputState(data, true, extra?.elapsed || 0);

        if (operation === "single_pass_extraction") {
          updateCustomTool({ isSinglePassExtractLoading: false });
        }
        clearPromptStatuses(
          extra?.prompt_ids,
          extra?.document_id,
          extra?.profile_manager_id,
        );
        setAlertDetails({
          type: "success",
          content:
            operation === "single_pass_extraction"
              ? "Single pass extraction completed successfully."
              : "Prompt execution completed successfully.",
        });
      } else if (operation === "index_document") {
        const docId = result?.document_id;
        if (docId) {
          deleteIndexDoc(docId);
        }
        setAlertDetails({
          type: "success",
          content: `${selectedDoc?.document_name || "Document"} - Indexed successfully`,
        });
      }
    },
    [
      updatePromptOutputState,
      promptOutputApi,
      clearPromptStatuses,
      updateCustomTool,
      setAlertDetails,
      deleteIndexDoc,
      selectedDoc,
      details,
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
        const { status, operation, result, error, tool_id, ...extra } = msg;

        // Ignore events belonging to a different tool (multi-tab safety)
        if (tool_id && details?.tool_id && tool_id !== details.tool_id) {
          return;
        }

        // Captured before handling so a handler throw doesn't hide the outcome.
        setPostHogCustomEvent("ps_prompt_run_result", {
          task_id: extra?.task_id,
          operation,
          status,
          tool_id,
          prompt_count: extra?.prompt_ids?.length,
          elapsed_seconds: extra?.elapsed,
        });

        if (status === "completed") {
          handleCompleted(operation, result, extra);
        } else if (status === "failed") {
          handleFailed(operation, error, extra);
        }
      } catch (err) {
        setAlertDetails(
          handleException(err, "Failed to process prompt studio result"),
        );
      }
    },
    [
      handleCompleted,
      handleFailed,
      setAlertDetails,
      handleException,
      details,
      setPostHogCustomEvent,
    ],
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
