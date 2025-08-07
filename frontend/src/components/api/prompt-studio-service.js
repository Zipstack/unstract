import { useCallback } from "react";

import useRequestUrl from "../../hooks/useRequestUrl";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";

export const usePromptStudioService = () => {
  const axiosPrivate = useAxiosPrivate();
  const { getUrl } = useRequestUrl();
  const getPromptStudioCount = useCallback(async () => {
    const response = await axiosPrivate({
      method: "GET",
      url: getUrl("/tool/prompt-studio/count/"),
    });
    return response.data.count;
  }, [axiosPrivate, getUrl]);

  const getRetrievalStrategies = useCallback(
    async (toolId) => {
      const response = await axiosPrivate({
        method: "GET",
        url: getUrl(`/prompt-studio/${toolId}/get_retrieval_strategies`),
      });
      return response.data;
    },
    [axiosPrivate, getUrl]
  );

  return { getPromptStudioCount, getRetrievalStrategies };
};
