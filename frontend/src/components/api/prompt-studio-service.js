import axios from "axios";
import { useSessionStore } from "../../store/session-store";

export const promptStudioService = () => {
  const getPromptStudioCount = async () => {
    const { sessionDetails } = useSessionStore.getState();
    if (!sessionDetails) {
      throw new Error("Session details are missing");
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails.orgId}/tool/prompt-studio/`,
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
