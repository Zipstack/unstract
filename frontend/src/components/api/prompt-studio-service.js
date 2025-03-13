import useRequestUrl from "../../hooks/useRequestUrl";
import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";

export const usePromptStudioService = () => {
  const axiosPrivate = useAxiosPrivate();
  const { getUrl } = useRequestUrl();

  const getPromptStudioCount = async () => {
    const response = await axiosPrivate({
      method: "GET",
      url: getUrl("/tool/prompt-studio/"),
    });

    return response.data.count;
  };

  return { getPromptStudioCount };
};
