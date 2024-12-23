import { useParams } from "react-router-dom";

import { useCustomToolStore } from "../store/custom-tool-store";
import { usePromptOutputStore } from "../store/prompt-output-store";
import { useSessionStore } from "../store/session-store";
import { useTokenUsageStore } from "../store/token-usage-store";
import { useAxiosPrivate } from "./useAxiosPrivate";

let promptOutputApiSps;
try {
  promptOutputApiSps =
    require("../plugins/simple-prompt-studio/helper").promptOutputApiSps;
} catch {
  // The component will remain null of it is not available
}
let publicOutputsApi;
try {
  publicOutputsApi =
    require("../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicOutputsApi;
} catch {
  // The component will remain null of it is not available
}

const usePromptOutput = () => {
  const { sessionDetails } = useSessionStore();
  const { setTokenUsage, updateTokenUsage } = useTokenUsageStore();
  const { setPromptOutput, updatePromptOutput } = usePromptOutputStore();
  const { isSimplePromptStudio, isPublicSource, selectedDoc } =
    useCustomToolStore();
  const axiosPrivate = useAxiosPrivate();
  const { id } = useParams();

  const generatePromptOutputKey = (
    promptId,
    docId,
    llmProfile,
    isSinglePass,
    isIncludeSinglePass = true
  ) => {
    let key = `${promptId}__${docId}__${llmProfile}`;

    if (isIncludeSinglePass) {
      key += `__${isSinglePass}`;
    }
    return key;
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

    if (isSimplePromptStudio) {
      url = promptOutputApiSps(toolId, null, null);
    }

    if (isPublicSource) {
      url = publicOutputsApi(id, promptId, isSinglePassExtract, null, null);
    }

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

  const updatePromptOutputState = (data, isReset, timer = 0) => {
    const outputs = {};

    let isTokenUsageForSinglePassAdded = false;
    const tokenUsageDetails = {};
    data.forEach((item) => {
      const promptId = item?.prompt_id;
      const docId = item?.document_manager;
      const llmProfile = item?.profile_manager;
      const isSinglePass = item?.is_single_pass_extract;

      if (!promptId || !docId || !llmProfile) {
        return;
      }

      const key = generatePromptOutputKey(
        promptId,
        docId,
        llmProfile,
        isSinglePass,
        true
      );
      outputs[key] = {
        runId: item?.run_id,
        promptOutputId: item?.prompt_output_id,
        profileManager: llmProfile,
        context: item?.context,
        challengeData: item?.challenge_data,
        tokenUsage: item?.token_usage,
        output: item?.output,
        timer,
        coverage: item?.coverage,
      };

      if (item?.is_single_pass_extract && isTokenUsageForSinglePassAdded)
        return;

      if (item?.is_single_pass_extract) {
        const tokenUsageId = generatePromptOutputKeyForSinglePass(
          llmProfile,
          docId
        );
        tokenUsageDetails[tokenUsageId] = item?.token_usage;
        tokenUsageDetails[
          generatePromptOutputKeyForContext(llmProfile, docId)
        ] = item?.context;
        tokenUsageDetails[
          generatePromptOutputKeyForChallenge(llmProfile, docId)
        ] = item?.challenge_data;
        isTokenUsageForSinglePassAdded = true;
        return;
      }

      const tokenUsageId = generatePromptOutputKey(
        promptId,
        docId,
        llmProfile,
        false,
        false
      );
      tokenUsageDetails[tokenUsageId] = item?.token_usage;
    });
    if (isReset) {
      setPromptOutput(outputs);
      setTokenUsage(tokenUsageDetails);
    } else {
      const prevOutputs = usePromptOutputStore.getState().promptOutputs;
      updatePromptOutput(updateCoverage(prevOutputs, outputs));
      updateTokenUsage(tokenUsageDetails);
    }
  };

  const updateCoverage = (promptOutputs, outputs) => {
      let updatedPromptOutputs = promptOutputs;
      Object.keys(outputs).forEach((key) => {
      const [keyPromptId, keyDoctId, , keyIsSinglePass] = key.split("__");
        // only add output of selected document
        if (keyDoctId === selectedDoc?.document_id) {
          const currentOutput = { [key]: outputs[key] };
          updatedPromptOutputs = { ...promptOutputs, ...currentOutput };
        }
        Object.keys(updatedPromptOutputs).forEach((innerKey) => {
        const [existingPromptId, , , existingIsSinglePass] =
            innerKey.split("__"); // Extract promptId from key
          if (
            keyPromptId === existingPromptId &&
            keyIsSinglePass === existingIsSinglePass
          ) {
            updatedPromptOutputs[innerKey].coverage = outputs[key]?.coverage;
          }
        });
      });
    return updatedPromptOutputs;
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

    return axiosPrivate(requestOptions)
      .then((res) => res)
      .catch((err) => err);
  };

  return {
    promptOutputApi,
    updatePromptOutputState,
    generatePromptOutputKey,
  };
};

export default usePromptOutput;
