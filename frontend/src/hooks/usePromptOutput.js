import { useSessionStore } from "../store/session-store";
import { useAxiosPrivate } from "./useAxiosPrivate";

const usePromptOutput = () => {
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();

  const generatePromptOutputKey = (
    promptId,
    docId,
    llmProfile,
    isSinglePass
  ) => {
    return `${promptId}__${docId}__${llmProfile}__${isSinglePass}`;
  };

  const generatePromptOutputKeyForSinglePass = (llmProfile, docId) => {
    return `single_pass__${llmProfile}__${docId}`;
  };

  const generatePromptOutputKeyForContext = (llmProfile, docId) => {
    return `single_pass__${llmProfile}__${docId}__context`;
  };

  const generatePromptOutputKeyForChallenge = (llmProfile, docId) => {
    return `single_pass__${llmProfile}__${docId}__challenge_data`;
  };

  const getUrl = (toolId, docId, promptId, llmProfile, isSinglePassExtract) => {
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${toolId}`;

    if (docId) {
      url += `&document_manager=${docId}`;
    }

    if (promptId) {
      url += `&prompt_id=${promptId}`;
    }

    if (llmProfile) {
      url += `&profile_manager=${llmProfile}`;
    }

    if (isSinglePassExtract) {
      url += `&is_single_pass_extract=${isSinglePassExtract}`;
    }

    return url;
  };

  const promptOutputApi = async (
    toolId,
    docId = null,
    promptId = null,
    llmProfile = null,
    isSinglePassExtract = false
  ) => {
    const url = getUrl(
      toolId,
      docId,
      promptId,
      llmProfile,
      isSinglePassExtract
    );
    const requestOptions = {
      method: "GET",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    return axiosPrivate(requestOptions);
  };

  return {
    promptOutputApi,
    generatePromptOutputKey,
    generatePromptOutputKeyForSinglePass,
    generatePromptOutputKeyForContext,
    generatePromptOutputKeyForChallenge,
  };
};

export default usePromptOutput;
