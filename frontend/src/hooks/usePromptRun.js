import {
  generateApiRunStatusId,
  generateUUID,
  pollForCompletion,
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

const usePromptRun = () => {
  const { pushPromptRunApi, freeActiveApi } = usePromptRunQueueStore();
  const { generatePromptOutputKey, updatePromptOutputState } =
    usePromptOutput();
  const { addPromptStatus, removePromptStatus } = usePromptRunStatusStore();
  const { details, llmProfiles, listOfDocs, selectedDoc } =
    useCustomToolStore();
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

    const startTime = Date.now();
    const maxWaitTime = 30 * 1000; // 30 seconds
    const pollingInterval = 5000; // 5 seconds

    pollForCompletion(
      startTime,
      requestOptions,
      maxWaitTime,
      pollingInterval,
      makeApiRequest
    )
      .then((res) => {
        if (docId !== selectedDoc?.document_id) return;
        const data = res?.data || [];
        const timeTakenInSeconds = Math.floor((Date.now() - startTime) / 1000);
        updatePromptOutputState(data, false, timeTakenInSeconds);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to generate prompt output")
        );
      })
      .finally(() => {
        freeActiveApi();
        const statusKey = generateApiRunStatusId(docId, profileId);
        removePromptStatus(promptId, statusKey);
      });
  };

  const runPrompt = (listOfApis) => {
    if (!listOfApis?.length) return;
    listOfApis.forEach(runPromptApi);
  };

  const prepareApiRequests = (promptIds, profileIds, docIds) => {
    const apiRequestsToQueue = [];
    const promptRunApiStatus = {};

    promptIds.forEach((promptId) => {
      if (!promptRunApiStatus[promptId]) {
        promptRunApiStatus[promptId] = {};
      }
      profileIds.forEach((profileId) => {
        docIds.forEach((docId) => {
          const key = generatePromptOutputKey(
            promptId,
            docId,
            profileId,
            null,
            false
          );
          const statusKey = generateApiRunStatusId(docId, profileId);
          promptRunApiStatus[promptId][statusKey] =
            PROMPT_RUN_API_STATUSES.RUNNING;
          apiRequestsToQueue.push(key);
        });
      });
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
    docId = null
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

    switch (promptRunType) {
      case PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ONE_DOC:
        if (!promptId || !profileId || !docId) return;
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          [promptId],
          [profileId],
          [docId]
        ));
        break;

      case PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ALL_DOCS:
        if (!promptId || !profileId) return;
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          [promptId],
          [profileId],
          docIds
        ));
        break;

      case PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ONE_DOC:
        if (!promptId || !docId) return;
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          [promptId],
          profileIds,
          [docId]
        ));
        break;

      case PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ALL_DOCS:
        if (!promptId) return;
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          [promptId],
          profileIds,
          docIds
        ));
        break;

      case PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ONE_DOC:
        if (!docId) return;
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          promptIds,
          profileIds,
          [docId]
        ));
        break;

      case PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ALL_DOCS:
        ({ apiRequestsToQueue, promptRunApiStatus } = prepareApiRequests(
          promptIds,
          profileIds,
          docIds
        ));
        break;

      default:
        return;
    }

    addPromptStatus(promptRunApiStatus);
    pushPromptRunApi(apiRequestsToQueue);
  };

  return {
    runPrompt,
    handlePromptRunRequest,
    syncPromptRunApisAndStatus,
  };
};

export default usePromptRun;
