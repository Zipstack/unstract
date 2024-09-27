import {
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
  const { addPromptStatus } = usePromptRunStatusStore();
  const { details, llmProfiles, listOfDocs, selectedDoc } =
    useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const runPrompt = (listOfApis) => {
    if (!listOfApis || !listOfApis?.length) {
      return;
    }

    listOfApis.forEach((api) => {
      runPromptApi(api);
    });
  };

  const runPromptApi = (api) => {
    const { promptId, docId, profileId } = api;
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

    const makeApiRequest = (requestOptions) => {
      return axiosPrivate(requestOptions);
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
        const endTime = Date.now();
        const timeTakenInSeconds = Math.floor((endTime - startTime) / 1000);
        updatePromptOutputState(data, false, timeTakenInSeconds);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, `Failed to generate prompt output`)
        );
      })
      .finally(() => {
        freeActiveApi();
        const key = generatePromptOutputKey(
          promptId,
          docId,
          profileId,
          null,
          false
        );
        const promptRunApiStatus = {
          [key]: PROMPT_RUN_API_STATUSES.COMPLETED,
        };
        addPromptStatus(promptRunApiStatus);
      });
  };

  const syncPromptRunApisAndStatus = (promptApis) => {
    const promptRunApiStatus = {};
    promptApis.forEach((promptApiDetails) => {
      const key = generatePromptOutputKey(
        promptApiDetails?.promptId,
        promptApiDetails?.docId,
        promptApiDetails?.profileId,
        false,
        false
      );
      promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;
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
    if (promptRunType === PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ONE_DOC) {
      if (!promptId || !profileId || !docId) return;

      const key = generatePromptOutputKey(
        promptId,
        docId,
        profileId,
        null,
        false
      );
      const promptRunApiStatus = {
        [key]: PROMPT_RUN_API_STATUSES.RUNNING,
      };
      const apiRequestsToQueue = [
        {
          promptId,
          profileId,
          docId,
        },
      ];

      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }

    if (promptRunType === PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ONE_LLM_ALL_DOCS) {
      if (!promptId || !profileId) return;

      const apiRequestsToQueue = [];
      const promptRunApiStatus = {};
      [...listOfDocs].forEach((doc) => {
        const docId = doc?.document_id;
        const key = generatePromptOutputKey(
          promptId,
          docId,
          profileId,
          null,
          false
        );
        promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;
        apiRequestsToQueue.push({
          promptId,
          profileId,
          docId,
        });
      });
      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }

    if (promptRunType === PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ONE_DOC) {
      if (!promptId || !docId) return;

      const apiRequestsToQueue = [];
      const promptRunApiStatus = {};
      [...llmProfiles].forEach((profile) => {
        const profileId = profile?.profile_id;
        const key = generatePromptOutputKey(
          promptId,
          docId,
          profileId,
          null,
          false
        );
        promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;

        apiRequestsToQueue.push({
          promptId,
          profileId,
          docId,
        });
      });
      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }

    if (promptRunType === PROMPT_RUN_TYPES.RUN_ONE_PROMPT_ALL_LLMS_ALL_DOCS) {
      if (!promptId) return;

      const apiRequestsToQueue = [];
      const promptRunApiStatus = {};
      [...listOfDocs].forEach((doc) => {
        [...llmProfiles].forEach((profile) => {
          const docId = doc?.document_id;
          const profileId = profile?.profile_id;
          const key = generatePromptOutputKey(
            promptId,
            docId,
            profileId,
            null,
            false
          );
          promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;
          apiRequestsToQueue.push({
            promptId,
            profileId,
            docId,
          });
        });
      });
      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }

    const listOfPrompts = details?.prompts || [];
    if (promptRunType === PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ONE_DOC) {
      if (!docId) return;

      const apiRequestsToQueue = [];
      const promptRunApiStatus = {};
      [...listOfPrompts].forEach((prompt) => {
        [...llmProfiles].forEach((profile) => {
          const promptId = prompt?.prompt_id;
          const profileId = profile?.profile_id;
          const key = generatePromptOutputKey(
            promptId,
            docId,
            profileId,
            null,
            false
          );
          promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;
          apiRequestsToQueue.push({
            promptId,
            profileId,
            docId,
          });
        });
      });
      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }

    if (promptRunType === PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ONE_LLM_ALL_DOCS) {
      const apiRequestsToQueue = [];
      const promptRunApiStatus = {};
      [...listOfPrompts].forEach((prompt) => {
        [...listOfDocs].forEach((doc) => {
          [...llmProfiles].forEach((profile) => {
            const promptId = prompt?.prompt_id;
            const docId = doc?.document_id;
            const profileId = profile?.profile_id;
            const key = generatePromptOutputKey(
              promptId,
              docId,
              profileId,
              null,
              false
            );
            promptRunApiStatus[key] = PROMPT_RUN_API_STATUSES.RUNNING;
            apiRequestsToQueue.push({
              promptId,
              profileId,
              docId,
            });
          });
        });
      });
      addPromptStatus(promptRunApiStatus);
      pushPromptRunApi(apiRequestsToQueue);

      return;
    }
  };

  return {
    runPrompt,
    syncPromptRunApisAndStatus,
    handlePromptRunRequest,
  };
};

export default usePromptRun;
