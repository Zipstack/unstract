import {
  generateApiRunStatusId,
  generateUUID,
  PROMPT_RUN_API_STATUSES,
  PROMPT_RUN_TYPES,
} from "../helpers/GetStaticData";
import { useAlertStore } from "../store/alert-store";
import { useCustomToolStore } from "../store/custom-tool-store";
import { usePromptRunQueueStore } from "../store/prompt-run-queue-store";
import { usePromptRunStatusStore } from "../store/prompt-run-status-store";
import { useSessionStore } from "../store/session-store";
import { useAxiosPrivate } from "./useAxiosPrivate";
import { useExceptionHandler } from "./useExceptionHandler";
import usePromptOutput from "./usePromptOutput";

// Tracks the latest run nonce per (promptId, statusKey) so stale timeouts
// from a previous run don't falsely cancel a newer run of the same combo.
const runNonceMap = new Map();
const SOCKET_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

const usePromptRun = () => {
  const { pushPromptRunApi, freeActiveApi } = usePromptRunQueueStore();
  const { generatePromptOutputKey } = usePromptOutput();
  const { addPromptStatus, removePromptStatus } = usePromptRunStatusStore();
  const { details, llmProfiles, listOfDocs } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const makeApiRequest = (requestOptions) => axiosPrivate(requestOptions);

  const runPromptApi = (api) => {
    const [promptId, docId, profileId] = api.split("__");
    const runId = generateUUID();

    const body = {
      id: promptId,
      document_id: docId,
      profile_manager: profileId,
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

    // Fire-and-forget: POST dispatches the Celery task, socket delivers result.
    const statusKey = generateApiRunStatusId(docId, profileId);
    const nonceKey = `${promptId}__${statusKey}`;
    const nonce = generateUUID();
    runNonceMap.set(nonceKey, nonce);

    makeApiRequest(requestOptions)
      .then((res) => {
        // Handle pending-indexing response: clear running status immediately
        if (res?.data?.status === "pending") {
          removePromptStatus(promptId, statusKey);
          setAlertDetails({
            type: "info",
            content:
              res?.data?.message || "Document is being indexed. Please wait.",
          });
          return;
        }

        // Timeout safety net: clear stale status if socket event never arrives.
        // Only clears if this is still the latest run for this combo.
        setTimeout(() => {
          if (runNonceMap.get(nonceKey) !== nonce) {
            return;
          }
          const current = usePromptRunStatusStore.getState().promptRunStatus;
          if (
            current?.[promptId]?.[statusKey] === PROMPT_RUN_API_STATUSES.RUNNING
          ) {
            removePromptStatus(promptId, statusKey);
            setAlertDetails({
              type: "warning",
              content: "Prompt execution timed out. Please try again.",
            });
          }
          runNonceMap.delete(nonceKey);
        }, SOCKET_TIMEOUT_MS);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate prompt output"),
        );
        removePromptStatus(promptId, statusKey);
        runNonceMap.delete(nonceKey);
      })
      .finally(() => {
        freeActiveApi();
      });
  };

  const runBulkPromptApi = (promptIds, docId, profileId) => {
    const runId = generateUUID();
    const body = {
      prompt_ids: promptIds,
      document_id: docId,
      profile_manager: profileId,
      run_id: runId,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/bulk_fetch_response/${details?.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    const statusKey = generateApiRunStatusId(docId, profileId);
    const nonces = {};
    promptIds.forEach((promptId) => {
      const nonceKey = `${promptId}__${statusKey}`;
      const nonce = generateUUID();
      nonces[promptId] = nonce;
      runNonceMap.set(nonceKey, nonce);
    });

    // Timeout safety net: clear stale status if socket event never arrives.
    // Only clears if this is still the latest run for each prompt combo.
    const clearStaleStatuses = () => {
      promptIds.forEach((promptId) => {
        const nonceKey = `${promptId}__${statusKey}`;
        if (runNonceMap.get(nonceKey) !== nonces[promptId]) {
          return;
        }
        const current = usePromptRunStatusStore.getState().promptRunStatus;
        if (
          current?.[promptId]?.[statusKey] === PROMPT_RUN_API_STATUSES.RUNNING
        ) {
          removePromptStatus(promptId, statusKey);
        }
        runNonceMap.delete(nonceKey);
      });
    };

    makeApiRequest(requestOptions)
      .then((res) => {
        if (res?.data?.status === "pending") {
          promptIds.forEach((promptId) => {
            removePromptStatus(promptId, statusKey);
          });
          setAlertDetails({
            type: "info",
            content:
              res?.data?.message || "Document is being indexed. Please wait.",
          });
          return;
        }

        setTimeout(clearStaleStatuses, SOCKET_TIMEOUT_MS);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate prompt output"),
        );
        promptIds.forEach((promptId) => {
          const nonceKey = `${promptId}__${statusKey}`;
          removePromptStatus(promptId, statusKey);
          runNonceMap.delete(nonceKey);
        });
      })
      .finally(() => {
        freeActiveApi();
      });
  };

  const runPrompt = (listOfApis) => {
    if (!listOfApis?.length) {
      return;
    }
    listOfApis.forEach(runPromptApi);
  };

  const prepareApiRequests = (promptIds, profileIds, docIds) => {
    const apiRequestsToQueue = [];
    const promptRunApiStatus = [];
    const combinations = [];

    for (const promptId of promptIds) {
      for (const profileId of profileIds) {
        for (const docId of docIds) {
          combinations.push({ promptId, profileId, docId });
        }
      }
    }

    combinations.forEach(({ promptId, profileId, docId }) => {
      if (!promptRunApiStatus[promptId]) {
        promptRunApiStatus[promptId] = {};
      }
      const key = generatePromptOutputKey(
        promptId,
        docId,
        profileId,
        null,
        false,
      );
      const statusKey = generateApiRunStatusId(docId, profileId);
      promptRunApiStatus[promptId][statusKey] = PROMPT_RUN_API_STATUSES.RUNNING;
      apiRequestsToQueue.push(key);
    });

    return { apiRequestsToQueue, promptRunApiStatus };
  };

  const syncPromptRunApisAndStatus = (promptApis) => {
    const promptRunApiStatus = {};

    promptApis.forEach((apiDetails) => {
      const [promptId, docId, profileId] = apiDetails.split("__");
      const statusKey = generateApiRunStatusId(docId, profileId);

      if (!promptRunApiStatus[promptId]) {
        promptRunApiStatus[promptId] = {};
      }

      promptRunApiStatus[promptId][statusKey] = PROMPT_RUN_API_STATUSES.RUNNING;
    });

    addPromptStatus(promptRunApiStatus);
    pushPromptRunApi(promptApis);
  };

  const handlePromptRunRequest = (
    promptRunType,
    promptId = null,
    profileId = null,
    docId = null,
  ) => {
    const promptIds = promptId
      ? [promptId]
      : details?.prompts.map((p) => p.prompt_id) || [];
    const profileIds = profileId
      ? [profileId]
      : llmProfiles.map((p) => p.profile_id) || [];
    const docIds = docId ? [docId] : listOfDocs.map((d) => d.document_id) || [];

    let apiRequestsToQueue = [];
    let promptRunApiStatus = {};

    const paramsMap = {
      [PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ONE_DOC]: {
        requiredParams: ["promptId", "profileId", "docId"],
        prompts: [promptId],
        profiles: [profileId],
        docs: [docId],
      },
      [PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ALL_DOCS]: {
        requiredParams: ["promptId", "profileId"],
        prompts: [promptId],
        profiles: [profileId],
        docs: docIds,
      },
      [PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ONE_DOC]: {
        requiredParams: ["promptId", "docId"],
        prompts: [promptId],
        profiles: profileIds,
        docs: [docId],
      },
      [PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ALL_DOCS]: {
        requiredParams: ["promptId"],
        prompts: [promptId],
        profiles: profileIds,
        docs: docIds,
      },
      [PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ONE_DOC]: {
        requiredParams: ["docId"],
        prompts: promptIds,
        profiles: profileIds,
        docs: [docId],
      },
      [PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ALL_DOCS]: {
        requiredParams: [],
        prompts: promptIds,
        profiles: profileIds,
        docs: docIds,
      },
    };

    const params = paramsMap[promptRunType];
    if (!params) {
      return;
    }

    const paramValues = { promptId, profileId, docId };
    const missingParams = params.requiredParams.filter(
      (param) => !paramValues[param],
    );

    if (missingParams.length > 0) {
      return;
    }

    ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
      params.prompts,
      params.profiles,
      params.docs,
    ));

    addPromptStatus(promptRunApiStatus);

    // Use bulk API when multiple prompts target the same (profile, doc) to
    // prevent the "Document being indexed" race condition.
    const isBulk = params.prompts.length > 1;
    if (isBulk) {
      for (const pId of params.profiles) {
        for (const dId of params.docs) {
          runBulkPromptApi(params.prompts, dId, pId);
        }
      }
    } else {
      pushPromptRunApi(apiRequestsToQueue);
    }
  };

  return {
    runPrompt,
    handlePromptRunRequest,
    syncPromptRunApisAndStatus,
  };
};

export default usePromptRun;
