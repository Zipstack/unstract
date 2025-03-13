import axios from "axios";
import { useSessionStore } from "../../store/session-store";
import useRequestUrl from "../../hooks/useRequestUrl";

export const promptStudioService = () => {
  const { getUrl } = useRequestUrl();
  const getPromptStudioCount = async () => {
    const { sessionDetails } = useSessionStore.getState();
    if (!sessionDetails) {
      throw new Error("Session details are missing");
    }

    const requestOptions = {
      method: "GET",
      url: getUrl("/tool/prompt-studio/"),
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails.csrfToken,
      },
    };
    const response = await axios(requestOptions);
    return response.data.count;
  };

  return { getPromptStudioCount };
};
